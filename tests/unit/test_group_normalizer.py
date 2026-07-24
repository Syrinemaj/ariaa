"""
Unit tests — group_normalizer.py (grouped-endpoint LLM normalization).

The LLM is never called for real: `ai_client` is a stub object exposing
`structured_chat(...)`, so these tests only exercise the grouping logic,
the rules-vs-LLM decision, and the response validation/fallback rules.
"""
from __future__ import annotations

from typing import Any

from app.normalization.dynamic_segment_detector import (
    detect_dynamic_positions,
    is_position_dynamic_for_entry,
)
from app.normalization.group_normalizer import build_group_hints, get_stats, reset_stats


def _raw_segments(path: str) -> list[str]:
    return [s for s in path.split("/") if s]


def _dynamic_by_shape(entries: list[tuple[str, str]]) -> list[set]:
    """
    Mirrors service.py's per-entry validation: build_group_hints() now takes
    one already-validated position set per entry (not the coarse
    (method, length)-keyed dict) — see ARIA-NORM-FIX in
    dynamic_segment_detector.py / group_normalizer.py.
    """
    all_segments = [_raw_segments(p) for _, p in entries]
    dynamic = detect_dynamic_positions([(m, segs) for (m, _), segs in zip(entries, all_segments)])

    same_shape: dict = {}
    for (method, _), segs in zip(entries, all_segments):
        same_shape.setdefault((method.upper(), len(segs)), []).append(segs)

    return [
        {
            pos for pos in dynamic.get((method.upper(), len(segs)), set())
            if is_position_dynamic_for_entry(segs, pos, same_shape[(method.upper(), len(segs))])
        }
        for (method, _), segs in zip(entries, all_segments)
    ]


class _StubGroqClient:
    """Records calls and returns a preset response — never hits the network."""

    def __init__(self, response: dict | None = None):
        self.response = response or {}
        self.calls: list[dict[str, Any]] = []

    def structured_chat(self, system_prompt, user_payload, json_schema, task_name="unknown"):
        self.calls.append(user_payload)
        return self.response


class TestNumericIdGroup:
    """Classic integer IDs: rules alone resolve this with high confidence —
    the LLM must not be called at all."""

    def test_numeric_group_stays_rules_only(self):
        reset_stats()
        entries = [
            ("GET", "/api/orders/123"),
            ("GET", "/api/orders/456"),
            ("GET", "/api/orders/789"),
        ]
        client = _StubGroqClient()

        hints = build_group_hints(entries, _dynamic_by_shape(entries), ai_client=client)

        assert hints == [None, None, None]
        assert client.calls == []
        assert get_stats().llm_calls == 0


class TestBusinessCodeGroup:
    """Non-standard business codes (prefixed_resource_id with an unknown
    prefix) are genuinely ambiguous under the rules pipeline (confidence
    0.45) — the group LLM call must fire and its high-confidence decision
    must be applied."""

    def test_unrecognized_business_code_triggers_llm(self):
        reset_stats()
        entries = [
            ("GET", "/api/widgets/wgt_alpha_009"),
            ("GET", "/api/widgets/wgt_beta_014"),
            ("GET", "/api/widgets/wgt_gamma_027"),
        ]
        llm_response = {
            "normalized_template": "/api/widgets/{id}",
            "segments": [
                {"value": "widgets", "position": 2, "is_id": False, "confidence": "high", "reason": "fixed"},
                {"value": "wgt_alpha_009", "position": 3, "is_id": True, "confidence": "high", "reason": "business code, variable across requests"},
            ],
        }
        client = _StubGroqClient(llm_response)

        hints = build_group_hints(entries, _dynamic_by_shape(entries), ai_client=client)

        assert len(client.calls) == 1
        assert set(client.calls[0]["urls_du_meme_endpoint"]) == {
            "/api/widgets/wgt_alpha_009",
            "/api/widgets/wgt_beta_014",
            "/api/widgets/wgt_gamma_027",
        }

        for hint in hints:
            assert hint is not None
            assert hint[2] == {
                "is_id": True,
                "confidence_label": "high",
                "reason": "business code, variable across requests",
            }

        stats = get_stats()
        assert stats.llm_calls == 1
        assert stats.fallback_single_example == 0
        assert stats.fallback_invalid_response == 0


class TestSingleExampleFallback:
    """A single observed URL gives no cross-request variability signal —
    must not call the LLM, must return confidence 'low' so the caller
    falls back to the existing rules pipeline."""

    def test_single_example_returns_low_confidence_without_llm_call(self):
        reset_stats()
        entries = [("GET", "/api/widgets/wgt_alpha_009")]
        client = _StubGroqClient()

        hints = build_group_hints(entries, _dynamic_by_shape(entries), ai_client=client)

        assert client.calls == []
        assert hints[0] == {
            2: {"is_id": None, "confidence_label": "low", "reason": "single example, no observable variability"}
        }

        stats = get_stats()
        assert stats.llm_calls == 0
        assert stats.fallback_single_example == 1


class TestInvalidResponseFallback:
    """Malformed/incomplete LLM output must fully fall back to rules —
    no partial application of a broken response."""

    def test_malformed_json_falls_back_completely(self):
        reset_stats()
        entries = [
            ("GET", "/api/widgets/wgt_alpha_009"),
            ("GET", "/api/widgets/wgt_beta_014"),
        ]
        client = _StubGroqClient({"unexpected": "shape"})

        hints = build_group_hints(entries, _dynamic_by_shape(entries), ai_client=client)

        assert hints == [None, None]
        stats = get_stats()
        assert stats.llm_calls == 1
        assert stats.fallback_invalid_response == 1


class TestLowConfidenceSegmentIgnored:
    """A segment the LLM itself flags 'low' confidence must not override
    the rules-based decision — the hint is recorded but marked low so
    normalize_path() ignores it."""

    def test_low_confidence_segment_is_not_applied(self):
        reset_stats()
        entries = [
            ("GET", "/api/widgets/wgt_alpha_009"),
            ("GET", "/api/widgets/wgt_beta_014"),
        ]
        llm_response = {
            "normalized_template": "/api/widgets/{id}",
            "segments": [
                {"value": "wgt_alpha_009", "position": 3, "is_id": True, "confidence": "low", "reason": "unsure"},
            ],
        }
        client = _StubGroqClient(llm_response)

        hints = build_group_hints(entries, _dynamic_by_shape(entries), ai_client=client)

        for hint in hints:
            assert hint[2]["confidence_label"] == "low"

        # Counted once per resolved position, not fanned out per sibling URL.
        assert get_stats().fallback_low_confidence_segments == 1
