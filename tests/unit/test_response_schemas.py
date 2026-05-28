"""Tests for Fix 2.4 — Pydantic validation on LLM responses."""
import pytest

from app.ai.response_schemas import ClassificationResponse, ParameterNameResponse


class TestClassificationResponse:
    def test_valid_response(self):
        raw = {
            "is_business_api": True,
            "should_keep": True,
            "business_domain": "Finance",
            "business_action": "create_invoice",
            "confidence": 0.95,
            "reason": "Matches billing endpoint pattern",
        }
        result = ClassificationResponse.model_validate(raw)
        assert result.is_business_api is True
        assert result.confidence == 0.95

    def test_confidence_clamped_at_1(self):
        # Hallucinated value 999 must be clamped to 1.0
        raw = {
            "is_business_api": True,
            "should_keep": True,
            "business_domain": None,
            "business_action": None,
            "confidence": 999,
            "reason": "ok",
        }
        result = ClassificationResponse.model_validate(raw)
        assert result.confidence == 1.0

    def test_confidence_clamped_at_0(self):
        raw = {
            "is_business_api": False,
            "should_keep": False,
            "business_domain": None,
            "business_action": None,
            "confidence": -5,
            "reason": "noise",
        }
        result = ClassificationResponse.model_validate(raw)
        assert result.confidence == 0.0

    def test_parse_llm_response_returns_fallback_on_bad_input(self):
        bad_raw = {"completely": "wrong", "structure": True}
        fallback = ClassificationResponse.fallback()
        result = ClassificationResponse.parse_llm_response(bad_raw, fallback)
        # Should return fallback, not raise
        assert result is fallback or result.confidence == 0.0

    def test_extra_fields_ignored(self):
        raw = {
            "is_business_api": False,
            "should_keep": False,
            "business_domain": None,
            "business_action": None,
            "confidence": 0.1,
            "reason": "telemetry",
            "UNEXPECTED_FIELD": "should be ignored",
        }
        result = ClassificationResponse.model_validate(raw)
        assert not hasattr(result, "UNEXPECTED_FIELD")


class TestParameterNameResponse:
    def test_valid(self):
        raw = {"parameter_name": "user_id", "confidence": 0.9}
        result = ParameterNameResponse.model_validate(raw)
        assert result.parameter_name == "user_id"
        assert result.confidence == 0.9

    def test_dangerous_chars_stripped(self):
        # Injection attempt in parameter name
        raw = {"parameter_name": "user'; DROP TABLE users--", "confidence": 0.5}
        result = ParameterNameResponse.model_validate(raw)
        assert "'" not in result.parameter_name
        assert ";" not in result.parameter_name
        assert "-" not in result.parameter_name

    def test_empty_name_becomes_param(self):
        raw = {"parameter_name": "---", "confidence": 0.0}
        result = ParameterNameResponse.model_validate(raw)
        assert result.parameter_name == "param"

    def test_fallback(self):
        fb = ParameterNameResponse.fallback("order_id")
        assert fb.parameter_name == "order_id"
        assert fb.confidence == 0.0
