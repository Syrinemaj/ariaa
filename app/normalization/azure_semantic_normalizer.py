import json
from typing import Any, Optional

from openai import AzureOpenAI

from app.core.config import settings


class AzureSemanticNormalizer:
    def __init__(self) -> None:
        self.client = AzureOpenAI(
            api_key=settings.AZURE_OPENAI_API_KEY,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            api_version=settings.AZURE_OPENAI_API_VERSION,
        )
        self.model = settings.AZURE_OPENAI_MODEL

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

        system_prompt = """
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

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "semantic_parameter_normalization",
                    "strict": True,
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
                },
            },
        )

        content = response.choices[0].message.content
        return json.loads(content)
