"""
Pydantic models for every LLM response shape produced by AzureOpenAIClient.

Why: json.loads() accepts any JSON structure including hallucinated fields
(e.g. confidence=999, missing required keys). These models enforce:
  - Required fields are present
  - Numeric ranges are sane (confidence ∈ [0, 1])
  - Unknown fields are silently ignored (extra="ignore")

Each model has a classmethod `parse_llm_response` that logs a warning and
returns a safe fallback on ValidationError instead of propagating the exception
to the caller — the pipeline can continue with degraded quality rather than crash.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

logger = logging.getLogger(__name__)


class _LLMResponseBase(BaseModel):
    model_config = {"extra": "ignore"}

    @classmethod
    def parse_llm_response(cls, raw: dict, fallback: "Self") -> "Self":  # type: ignore[name-defined]
        """
        Validate `raw` dict against this model.
        Returns `fallback` on validation failure (logs a warning with the error).
        """
        from pydantic import ValidationError
        try:
            return cls.model_validate(raw)
        except ValidationError as exc:
            logger.warning(
                "%s: LLM response failed validation — using fallback. raw=%s errors=%s",
                cls.__name__,
                str(raw)[:300],
                exc.errors(),
            )
            return fallback


# ─── HAR classification ───────────────────────────────────────────────────────

class ClassificationResponse(_LLMResponseBase):
    is_business_api: bool
    should_keep: bool
    business_domain: Optional[str] = None
    business_action: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str

    @field_validator("confidence", mode="before")
    @classmethod
    def clamp_confidence(cls, v: Any) -> float:
        # Guard against hallucinated values like 999 or "high"
        try:
            f = float(v)
        except (TypeError, ValueError):
            return 0.5
        return max(0.0, min(1.0, f))

    @classmethod
    def fallback(cls) -> "ClassificationResponse":
        return cls(
            is_business_api=False,
            should_keep=False,
            confidence=0.0,
            reason="validation_failed",
        )


# ─── URL parameter naming ─────────────────────────────────────────────────────

class ParameterNameResponse(_LLMResponseBase):
    parameter_name: str
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: Optional[str] = None

    @field_validator("confidence", mode="before")
    @classmethod
    def clamp_confidence(cls, v: Any) -> float:
        try:
            f = float(v)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(1.0, f))

    @field_validator("parameter_name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        # Strip dangerous characters; parameter names must be safe identifiers
        cleaned = "".join(c for c in v if c.isalnum() or c == "_").strip("_")
        return cleaned or "param"

    @classmethod
    def fallback(cls, raw_value: str = "param") -> "ParameterNameResponse":
        return cls(parameter_name=raw_value, confidence=0.0)


# ─── Generic structured chat ──────────────────────────────────────────────────

class StructuredChatResponse(_LLMResponseBase):
    """
    Generic wrapper for structured_chat() calls.
    The payload is kept as-is but must be a dict (not a list or scalar).
    """
    _data: dict

    @model_validator(mode="before")
    @classmethod
    def wrap_data(cls, values: Any) -> Any:
        if not isinstance(values, dict):
            raise ValueError(f"Expected dict from LLM, got {type(values).__name__}")
        return values

    @classmethod
    def fallback(cls) -> dict:
        return {}
