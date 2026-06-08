"""
Unit tests for LLM benchmark — token estimator and repository queries.
No database or LLM connection required.
"""
from unittest.mock import MagicMock, patch

import pytest

from app.llm_observability.token_estimator import (
    _estimate_completion,
    estimate_prompt_tokens,
    estimate_prompt_tokens_from_dict,
    estimate_run_cost,
)


# ── _estimate_completion ──────────────────────────────────────────────────────

class TestEstimateCompletion:
    def test_returns_ratio_of_prompt(self):
        result = _estimate_completion(1000, ratio=0.3)
        assert result == 300

    def test_capped_at_max_completion_tokens(self):
        # 100_000 * 0.3 = 30_000, but LLM_MAX_COMPLETION_TOKENS defaults to 1000
        result = _estimate_completion(100_000, ratio=0.3)
        from app.core.config import settings
        assert result == settings.LLM_MAX_COMPLETION_TOKENS

    def test_zero_prompt_returns_zero(self):
        assert _estimate_completion(0, ratio=0.3) == 0

    def test_small_prompt(self):
        result = _estimate_completion(100, ratio=0.25)
        assert result == 25


# ── estimate_prompt_tokens ────────────────────────────────────────────────────

class TestEstimatePromptTokens:
    def test_adds_system_overhead_for_known_task(self):
        text = "list all users"
        result = estimate_prompt_tokens(text, task_name="intent_analyzer")
        # Must be greater than pure token count
        from app.ai.token_counter import count_tokens
        from app.llm_observability.token_estimator import _SYSTEM_OVERHEAD
        raw = count_tokens(text)
        assert result == raw + _SYSTEM_OVERHEAD["intent_analyzer"]

    def test_uses_default_overhead_for_unknown_task(self):
        text = "hello world"
        result_known = estimate_prompt_tokens(text, task_name="intent_analyzer")
        result_unknown = estimate_prompt_tokens(text, task_name="nonexistent_task")
        from app.llm_observability.token_estimator import (
            _DEFAULT_OVERHEAD,
            _SYSTEM_OVERHEAD,
        )
        assert result_known != result_unknown
        from app.ai.token_counter import count_tokens
        assert result_unknown == count_tokens(text) + _DEFAULT_OVERHEAD

    def test_empty_task_name_uses_default(self):
        text = "test"
        result = estimate_prompt_tokens(text, task_name="")
        from app.ai.token_counter import count_tokens
        from app.llm_observability.token_estimator import _DEFAULT_OVERHEAD
        assert result == count_tokens(text) + _DEFAULT_OVERHEAD

    def test_longer_text_produces_more_tokens(self):
        short = estimate_prompt_tokens("hi", task_name="plan_builder")
        long = estimate_prompt_tokens(
            "list all users then update their email addresses and send notifications",
            task_name="plan_builder",
        )
        assert long > short


# ── estimate_prompt_tokens_from_dict ─────────────────────────────────────────

class TestEstimatePromptTokensFromDict:
    def test_dict_produces_more_tokens_than_empty(self):
        result = estimate_prompt_tokens_from_dict(
            {"method": "GET", "path": "/api/users", "description": "List all users"},
            task_name="plan_builder",
        )
        assert result > 0

    def test_empty_dict_still_has_overhead(self):
        result = estimate_prompt_tokens_from_dict({}, task_name="plan_builder")
        from app.llm_observability.token_estimator import _SYSTEM_OVERHEAD
        assert result >= _SYSTEM_OVERHEAD["plan_builder"]

    def test_larger_dict_produces_more_tokens(self):
        small = estimate_prompt_tokens_from_dict({"a": "b"})
        large = estimate_prompt_tokens_from_dict(
            {f"key_{i}": f"value_{i}" * 10 for i in range(20)}
        )
        assert large > small


# ── estimate_run_cost ─────────────────────────────────────────────────────────

class TestEstimateRunCost:
    ENDPOINTS = [
        {"method": "POST", "path": "/api/users", "description": "Create user"},
        {"method": "GET",  "path": "/api/users/{id}", "description": "Get user"},
    ]

    def test_returns_all_required_keys(self):
        result = estimate_run_cost("create a user", self.ENDPOINTS, plan_steps=2)
        assert "model" in result
        assert "phases" in result
        assert "total_estimated_prompt_tokens" in result
        assert "total_estimated_completion_tokens" in result
        assert "total_estimated_tokens" in result
        assert "estimated_cost_usd" in result
        assert "is_high_token_estimate" in result

    def test_phases_present(self):
        result = estimate_run_cost("create a user", self.ENDPOINTS, plan_steps=2)
        assert "intent_analysis" in result["phases"]
        assert "plan_building" in result["phases"]
        assert "plan_validation" in result["phases"]

    def test_zero_plan_steps_skips_validation(self):
        result = estimate_run_cost("create a user", self.ENDPOINTS, plan_steps=0)
        assert result["phases"]["plan_validation"]["estimated_prompt_tokens"] == 0
        assert result["phases"]["plan_validation"]["estimated_completion_tokens"] == 0

    def test_more_steps_increases_total_tokens(self):
        result_few = estimate_run_cost("create a user", self.ENDPOINTS, plan_steps=2)
        result_many = estimate_run_cost("create a user", self.ENDPOINTS, plan_steps=10)
        assert result_many["total_estimated_tokens"] > result_few["total_estimated_tokens"]

    def test_total_tokens_equals_sum_of_parts(self):
        result = estimate_run_cost("test instruction", self.ENDPOINTS, plan_steps=3)
        phases = result["phases"]
        expected_prompt = sum(
            p["estimated_prompt_tokens"] for p in phases.values()
        )
        expected_completion = sum(
            p["estimated_completion_tokens"] for p in phases.values()
        )
        assert result["total_estimated_prompt_tokens"] == expected_prompt
        assert result["total_estimated_completion_tokens"] == expected_completion
        assert result["total_estimated_tokens"] == expected_prompt + expected_completion

    def test_cost_is_non_negative(self):
        result = estimate_run_cost("any instruction", [], plan_steps=0)
        assert result["estimated_cost_usd"] >= 0

    def test_large_context_increases_plan_building_tokens(self):
        big_endpoints = [
            {"method": "GET", "path": f"/api/resource/{i}", "description": f"Resource {i}" * 20}
            for i in range(20)
        ]
        result_small = estimate_run_cost("test", self.ENDPOINTS, plan_steps=1)
        result_large = estimate_run_cost("test", big_endpoints, plan_steps=1)
        plan_small = result_small["phases"]["plan_building"]["estimated_prompt_tokens"]
        plan_large = result_large["phases"]["plan_building"]["estimated_prompt_tokens"]
        assert plan_large > plan_small

    def test_is_high_token_flag_type_is_bool(self):
        result = estimate_run_cost("instruction", [], plan_steps=0)
        assert isinstance(result["is_high_token_estimate"], bool)


# ── repository helper: _call_to_dict ─────────────────────────────────────────

class TestCallToDict:
    def test_estimation_delta_computed_when_both_present(self):
        from app.llm_observability.repository import _call_to_dict
        mock_call = MagicMock()
        mock_call.id = 1
        mock_call.task_name = "plan_builder"
        mock_call.model = "gpt-4o-mini"
        mock_call.prompt_tokens = 400
        mock_call.completion_tokens = 120
        mock_call.total_tokens = 520
        mock_call.estimated_cost_usd = 0.000312
        mock_call.is_high_token = False
        mock_call.estimated_prompt_tokens = 450
        mock_call.request_id = None
        mock_call.celery_task_id = None
        mock_call.called_at.isoformat.return_value = "2026-06-08T10:00:00+00:00"

        result = _call_to_dict(mock_call)
        assert result["estimation_delta"] == 50   # 450 - 400

    def test_estimation_delta_is_none_without_estimate(self):
        from app.llm_observability.repository import _call_to_dict
        mock_call = MagicMock()
        mock_call.estimated_prompt_tokens = None
        mock_call.prompt_tokens = 400
        mock_call.called_at.isoformat.return_value = "2026-06-08T10:00:00+00:00"

        result = _call_to_dict(mock_call)
        assert result["estimation_delta"] is None


# ── estimate_har_tokens ───────────────────────────────────────────────────────

def _make_har(entries: list[dict]) -> dict:
    return {"log": {"entries": entries}}


def _har_entry(
    method: str = "GET",
    url: str = "https://api.example.com/v1/users",
    status: int = 200,
    resp_mime: str = "application/json",
    req_body: str = "",
    resp_body: str = '{"id": 1}',
) -> dict:
    entry: dict = {
        "request": {
            "method": method,
            "url": url,
            "headers": [],
            "postData": {"mimeType": "application/json", "text": req_body} if req_body else None,
        },
        "response": {
            "status": status,
            "content": {"mimeType": resp_mime, "text": resp_body},
        },
    }
    return entry


class TestEstimateHarTokens:
    def test_returns_required_top_level_keys(self):
        from app.llm_observability.token_estimator import estimate_har_tokens
        har = _make_har([_har_entry()])
        result = estimate_har_tokens(har)
        assert "model" in result
        assert "har_stats" in result
        assert "min_estimate" in result
        assert "max_estimate" in result

    def test_har_stats_total_entries(self):
        from app.llm_observability.token_estimator import estimate_har_tokens
        har = _make_har([_har_entry(), _har_entry(method="POST")])
        result = estimate_har_tokens(har)
        assert result["har_stats"]["total_entries"] == 2

    def test_empty_har_returns_zeros(self):
        from app.llm_observability.token_estimator import estimate_har_tokens
        result = estimate_har_tokens({"log": {"entries": []}})
        assert result["har_stats"]["total_entries"] == 0
        assert result["min_estimate"]["total_tokens"] == 0
        assert result["max_estimate"]["total_tokens"] == 0

    def test_clear_api_entries_appear_in_both_scenarios(self):
        from app.llm_observability.token_estimator import estimate_har_tokens
        # POST + JSON + /api/ path → score 0.85, captured by both min and max
        entry = _har_entry(
            method="POST",
            url="https://example.com/api/v1/orders",
            req_body='{"item_id": 42}',
        )
        har = _make_har([entry])
        result = estimate_har_tokens(har)
        assert result["har_stats"]["min_api_candidates"] == 1
        assert result["har_stats"]["max_api_candidates"] == 1

    def test_borderline_entry_only_in_max(self):
        from app.llm_observability.token_estimator import estimate_har_tokens
        # GET + no JSON + no /api/ hint → score 0.05+0.10 = 0.15, below both thresholds
        # But a static asset (score ~0) should not appear in max either
        # Use a GET with /api/ hint but no JSON → score 0.05+0.25+0.10 = 0.40 → max only
        entry = _har_entry(
            method="GET",
            url="https://example.com/api/users",
            resp_mime="text/html",
        )
        har = _make_har([entry])
        result = estimate_har_tokens(har)
        # Score = 0.05 (GET) + 0.25 (api hint) + 0.10 (2xx) = 0.40 → max only
        assert result["har_stats"]["min_api_candidates"] == 0
        assert result["har_stats"]["max_api_candidates"] == 1

    def test_max_tokens_gte_min_tokens(self):
        from app.llm_observability.token_estimator import estimate_har_tokens
        entries = [
            _har_entry(method="POST", url="https://api.example.com/api/users",
                       req_body='{"name": "Alice"}'),
            _har_entry(method="GET", url="https://api.example.com/api/users/1"),
            _har_entry(method="PUT", url="https://api.example.com/api/users/1",
                       req_body='{"name": "Bob"}'),
        ]
        result = estimate_har_tokens(_make_har(entries))
        assert result["max_estimate"]["total_tokens"] >= result["min_estimate"]["total_tokens"]

    def test_breakdown_keys_present(self):
        from app.llm_observability.token_estimator import estimate_har_tokens
        entry = _har_entry(method="POST", url="https://api.example.com/api/items")
        result = estimate_har_tokens(_make_har([entry]))
        for scenario in ("min_estimate", "max_estimate"):
            bd = result[scenario]["breakdown"]
            assert "payload_classifier" in bd
            assert "normalizer" in bd
            assert "schema_inference" in bd
            assert "endpoint_understanding" in bd

    def test_larger_har_produces_more_tokens(self):
        from app.llm_observability.token_estimator import estimate_har_tokens
        small = _make_har([_har_entry(method="POST", url="https://api.example.com/api/x")])
        large = _make_har([
            _har_entry(
                method="POST",
                url=f"https://api.example.com/api/resource/{i}",
                req_body=f'{{"field_{i}": "value_{i}" * 20}}',
                resp_body=f'{{"id": {i}, "data": "x" * 100}}',
            )
            for i in range(10)
        ])
        small_result = estimate_har_tokens(small)
        large_result = estimate_har_tokens(large)
        assert large_result["max_estimate"]["total_tokens"] > small_result["max_estimate"]["total_tokens"]

    def test_cost_is_non_negative(self):
        from app.llm_observability.token_estimator import estimate_har_tokens
        result = estimate_har_tokens(_make_har([_har_entry()]))
        assert result["min_estimate"]["estimated_cost_usd"] >= 0
        assert result["max_estimate"]["estimated_cost_usd"] >= 0

    def test_missing_log_key_handled_gracefully(self):
        from app.llm_observability.token_estimator import estimate_har_tokens
        # har_data without "log" returns empty stats (the API layer raises 422)
        result = estimate_har_tokens({})
        assert result["har_stats"]["total_entries"] == 0
