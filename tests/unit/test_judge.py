"""evaluation/judge.py — judge_plan() now calls groq_client.structured_chat()
(app/ai/groq_client.py) instead of driving groq_client._sync directly, so it
gets the primary -> secondary -> tertiary -> Azure key fallback cascade for
free. These tests mock structured_chat() itself, not the raw OpenAI client.
"""
from unittest.mock import MagicMock

from evaluation.judge import JUDGE_MODEL_PREFERRED, judge_plan
from app.core.config import settings


def _case():
    return {
        "id": "tc_001", "category": "A", "instruction": "Crée 200 employés depuis ce CSV",
        "expected_steps_contain": ["POST /api/v1/employees"],
        "expected_field_mapping": True, "expected_loop": "csv_rows",
        "expected_confidence_min": 0.7,
    }


def _trace():
    return {
        "plan": {"selected_keys": ["POST /api/v1/employees"], "has_field_mapping": True, "has_loop": True,
                 "plan_confidence": 0.9, "reasoning": "r"},
        "intent": {"confidence": 0.9},
        "rag": {"rag_triggered": True},
    }


class TestJudgePlan:
    def test_preferred_model_succeeds_first_try(self):
        groq_client = MagicMock()
        groq_client.structured_chat.return_value = {
            "correctness": 5, "faithfulness": 5, "completeness": 4, "mapping": 5,
            "justification": "ok",
        }

        result = judge_plan(_case(), _trace(), groq_client)

        assert result["correctness"] == 5
        groq_client.structured_chat.assert_called_once()
        _, kwargs = groq_client.structured_chat.call_args
        assert kwargs["model"] == JUDGE_MODEL_PREFERRED
        assert kwargs["task_name"] == "judge_evaluation"

    def test_preferred_model_fails_falls_back_to_pipeline_model(self):
        groq_client = MagicMock()
        groq_client.structured_chat.side_effect = [
            Exception("model_decommissioned"),
            {"correctness": 4, "faithfulness": 5, "completeness": 3, "mapping": 4, "justification": "ok"},
        ]

        result = judge_plan(_case(), _trace(), groq_client)

        assert result["correctness"] == 4
        assert groq_client.structured_chat.call_count == 2
        first_kwargs = groq_client.structured_chat.call_args_list[0].kwargs
        second_kwargs = groq_client.structured_chat.call_args_list[1].kwargs
        assert first_kwargs["model"] == JUDGE_MODEL_PREFERRED
        assert second_kwargs["model"] == settings.GROQ_MODEL

    def test_both_models_fail_returns_error_dict_not_raise(self):
        groq_client = MagicMock()
        groq_client.structured_chat.side_effect = Exception("all keys exhausted")

        result = judge_plan(_case(), _trace(), groq_client)

        assert "error" in result
        assert "all keys exhausted" in result["error"]

    def test_user_payload_carries_full_formatted_prompt(self):
        # structured_chat() expects a dict user_payload (it gets
        # json.dumps()'d as the user turn) — not a raw string.
        groq_client = MagicMock()
        groq_client.structured_chat.return_value = {
            "correctness": 5, "faithfulness": 5, "completeness": 5, "mapping": 5, "justification": "ok",
        }

        judge_plan(_case(), _trace(), groq_client)

        _, kwargs = groq_client.structured_chat.call_args
        assert isinstance(kwargs["user_payload"], dict)
        prompt_text = next(iter(kwargs["user_payload"].values()))
        assert "Crée 200 employés depuis ce CSV" in prompt_text
        assert "POST /api/v1/employees" in prompt_text
