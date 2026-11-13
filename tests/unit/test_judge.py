"""evaluation/judge.py — judge_plan() calls ai_client.structured_chat(model=JUDGE_MODEL)
(app/ai/bedrock_client.py) with the model explicitly overridden, so the judge
always uses JUDGE_MODEL regardless of which model the ai_client instance was
constructed with. These tests mock structured_chat() itself.
"""
from unittest.mock import MagicMock

from evaluation.judge import JUDGE_MODEL, judge_plan


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
    def test_scores_plan_using_judge_model(self):
        ai_client = MagicMock()
        ai_client.structured_chat.return_value = {
            "correctness": 5, "faithfulness": 5, "completeness": 4, "mapping": 5,
            "justification": "ok",
        }

        result = judge_plan(_case(), _trace(), ai_client)

        assert result["correctness"] == 5
        ai_client.structured_chat.assert_called_once()
        _, kwargs = ai_client.structured_chat.call_args
        assert kwargs["model"] == JUDGE_MODEL
        assert kwargs["task_name"] == "judge_evaluation"

    def test_call_failure_returns_error_dict_not_raise(self):
        ai_client = MagicMock()
        ai_client.structured_chat.side_effect = Exception("validation error")

        result = judge_plan(_case(), _trace(), ai_client)

        assert "error" in result
        assert "validation error" in result["error"]
        ai_client.structured_chat.assert_called_once()

    def test_user_payload_carries_full_formatted_prompt(self):
        # structured_chat() expects a dict user_payload (it gets
        # json.dumps()'d as the user turn) — not a raw string.
        ai_client = MagicMock()
        ai_client.structured_chat.return_value = {
            "correctness": 5, "faithfulness": 5, "completeness": 5, "mapping": 5, "justification": "ok",
        }

        judge_plan(_case(), _trace(), ai_client)

        _, kwargs = ai_client.structured_chat.call_args
        assert isinstance(kwargs["user_payload"], dict)
        prompt_text = next(iter(kwargs["user_payload"].values()))
        assert "Crée 200 employés depuis ce CSV" in prompt_text
        assert "POST /api/v1/employees" in prompt_text
