"""
SemanticNormalizer — LLM-based URL path parameter naming.

Uses GroqClient (primary) with automatic Azure fallback.
Replaces AzureSemanticNormalizer which used AzureOpenAI directly
with the Azure-specific json_schema response format.
"""
from __future__ import annotations

from typing import Any, Optional

from app.ai.groq_client import GroqClient

_PARAM_SCHEMA: dict = {
    "name": "semantic_parameter_normalization",
    "schema": {
        "type": "object",
        "properties": {
            "parameter_name": {"type": "string"},
            "parameter_type": {"type": "string"},
            "confidence": {"type": "number"},
            "reason": {"type": "string"},
        },
        "required": ["parameter_name", "parameter_type", "confidence", "reason"],
        "additionalProperties": False,
    },
}

_SYSTEM_PROMPT = """
You are an API URL normalization engine.

Your task:
- infer the best semantic parameter name for a dynamic URL segment
- use URL context, request body and response body
- never invent endpoint paths
- output strict JSON only

Rules:
- parameter_name must be snake_case
- prefer business names like employee_id, invoice_id, customer_id
- if unclear, return generic_id
"""


class SemanticNormalizer:
    """
    LLM-based URL segment naming — provider-agnostic.
    One shared GroqClient instance per SemanticNormalizer object.
    """

    def __init__(self) -> None:
        self._client = GroqClient()

    def infer_parameter_name(
        self,
        method: str,
        path: str,
        raw_segment: str,
        previous_segment: Optional[str],
        next_segment: Optional[str],
        request_body: Any = None,
        response_body: Any = None,
    ) -> dict:
        payload = {
            "method": method,
            "path": path,
            "raw_segment": raw_segment,
            "previous_segment": previous_segment,
            "next_segment": next_segment,
            "request_body": request_body,
            "response_body": response_body,
        }

        return self._client.structured_chat(
            system_prompt=_SYSTEM_PROMPT,
            user_payload=payload,
            json_schema=_PARAM_SCHEMA,
            task_name="url_param_normalization",
        )
