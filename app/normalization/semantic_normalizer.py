"""
SemanticNormalizer — LLM-based URL path parameter naming.

Uses the AI client selected by settings.AI_PROVIDER (create_ai_client()) —
BedrockClient by default, GroqClient/AzureOpenAIClient as configured
alternatives. No fallback between providers is attempted here.

This is the last-resort, single-segment fallback: normalize_path() only
calls it when neither regex rules nor group_normalizer.py's group-level
comparison (siblings of the same endpoint, when available) could name the
segment with confidence >= 0.70. Since this path has no sibling context, the
prompt leans on payload-field matching and resource-name context instead —
see the DECISION ORDER below.
"""
from __future__ import annotations

from typing import Any, Optional

from app.ai.base_client import create_ai_client

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

_SYSTEM_PROMPT = """You are an API URL normalization engine, used as a last-resort fallback
when neither regex rules nor group-level comparison (siblings of the same
endpoint) could confidently name a dynamic URL segment.

INPUT you receive (JSON):
- method, path: the HTTP method and full path containing the segment
- raw_segment: the exact segment value to name
- previous_segment / next_segment: the path segments immediately around it
  (may be null at path boundaries)
- request_body / response_body: JSON payloads, when available — check these
  FIRST for a field whose value matches raw_segment (e.g. {"employee_id": 42})
  before guessing from the URL shape alone

DECISION ORDER (highest priority first):
1. A matching field name in request_body/response_body — reuse it verbatim.
2. previous_segment as a resource name (e.g. "employees" -> employee_id).
3. The raw_segment's own shape (numeric, hash-like, prefixed business code).
4. If none of the above gives a confident answer, return "generic_id" with confidence <= 0.5 — do not force a specific business name you cannot justify.

OUTPUT (strict JSON, matches the schema you were given):
- parameter_name: snake_case (e.g. employee_id, invoice_id, generic_id)
- confidence: 0.9-1.0 only when rule 1 applied, 0.7-0.9 for rule 2,
  0.5-0.7 for rule 3, <= 0.5 for rule 4 (unresolved)
- Never invent endpoint paths. Never return markdown or text outside the JSON object.

EXAMPLES

path=/employees/emp_a12, raw_segment="emp_a12", previous_segment="employees"
-> {"parameter_name": "employee_id", "parameter_type": "prefixed_id", "confidence": 0.8, "reason": "previous segment 'employees' is a known resource name"}

path=/webhooks/9f2a7b, raw_segment="9f2a7b", previous_segment="webhooks", response_body={"hook_id": "9f2a7b"}
-> {"parameter_name": "hook_id", "parameter_type": "string", "confidence": 0.95, "reason": "matches response_body field 'hook_id' exactly"}

path=/api/x7q, raw_segment="x7q", previous_segment="api", request_body=null, response_body=null
-> {"parameter_name": "generic_id", "parameter_type": "string", "confidence": 0.45, "reason": "no payload match, no resource-name context, non-standard short token — genuinely ambiguous"}"""


class SemanticNormalizer:
    """
    LLM-based URL segment naming — provider-agnostic.
    One shared GroqClient instance per SemanticNormalizer object.
    """

    def __init__(self) -> None:
        self._client = create_ai_client()

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
