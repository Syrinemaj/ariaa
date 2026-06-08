"""
GroqClient — primary LLM completion provider.

Uses the openai SDK pointed at Groq's OpenAI-compatible endpoint
(no extra package required beyond openai>=1.42.0).

Azure fallback
--------------
If Groq raises RateLimitError, APIError, or APITimeoutError, the client
automatically retries with AzureOpenAIClient — but only when
AZURE_OPENAI_API_KEY is configured. If Azure is also absent, the original
Groq exception is re-raised.

Embeddings
----------
Embeddings are NO LONGER handled by this client. Use LocalEmbeddingClient
(app/ai/local_embedding_client.py) for all vector operations.
The zero-vector fallback that existed here has been removed.

Interface
---------
Public methods match AzureOpenAIClient exactly so any code that receives an
ai_client via app.state or dependency injection works without changes:
  - classify_api_call(payload, db)     → ClassificationResponse
  - structured_chat(...)               → dict
  - structured_chat_async(...)         → dict  (async)
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from openai import APIError, APITimeoutError, AsyncOpenAI, OpenAI, RateLimitError
from sqlalchemy.orm import Session

from app.ai.response_schemas import ClassificationResponse
from app.ai.token_counter import truncate_dict_to_token_limit
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"

_CLASSIFY_SCHEMA: dict[str, Any] = {
    "name": "api_traffic_classification",
    "schema": {
        "type": "object",
        "properties": {
            "is_business_api": {"type": "boolean"},
            "should_keep": {"type": "boolean"},
            "business_domain": {"type": ["string", "null"]},
            "business_action": {"type": ["string", "null"]},
            "confidence": {"type": "number"},
            "reason": {"type": "string"},
        },
        "required": [
            "is_business_api", "should_keep", "business_domain",
            "business_action", "confidence", "reason",
        ],
        "additionalProperties": False,
    },
}


class GroqClient:
    """
    Groq LLM client — primary provider for all completions.
    Assign to app.state.ai_client in the FastAPI lifespan (see main.py).
    """

    def __init__(self) -> None:
        common = {"api_key": settings.GROQ_API_KEY, "base_url": _GROQ_BASE_URL}
        self._sync = OpenAI(**common)
        self._async = AsyncOpenAI(**common)

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _inject_schema(system_prompt: str, json_schema: dict[str, Any]) -> str:
        """
        Groq does not support response_format=json_schema (Azure strict mode).
        Embed the schema in the system prompt and use json_object mode instead.
        """
        schema_body = json_schema.get("schema", json_schema)
        return (
            f"{system_prompt}\n\n"
            "CRITICAL: Respond with a single valid JSON object matching the schema below.\n"
            "No markdown, no code fences, no extra keys, no explanation.\n"
            f"Required schema:\n{json.dumps(schema_body, indent=2)}"
        )

    @staticmethod
    def _log_usage(db: Optional[Session], task_name: str, usage: Any) -> None:
        if usage is None:
            return

        # Always increment Prometheus counters (no DB required).
        try:
            from app.core.config import settings as _s
            from app.observability.metrics import record_llm_tokens
            total = (usage.prompt_tokens or 0) + (usage.completion_tokens or 0)
            cost = (
                (usage.prompt_tokens or 0) / 1000 * _s.LLM_PROMPT_COST_PER_1K
                + (usage.completion_tokens or 0) / 1000 * _s.LLM_COMPLETION_COST_PER_1K
            )
            record_llm_tokens(
                task_name=task_name,
                model_name=settings.GROQ_MODEL,
                total_tokens=total,
                estimated_cost=cost,
                provider="groq",
            )
        except Exception:
            pass

        if db is not None:
            from app.llm_observability.service import log_llm_call_and_print_terminal_summary
            log_llm_call_and_print_terminal_summary(
                db=db,
                task_name=task_name,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
            )

    def _truncate(self, payload: dict[str, Any], task_name: str) -> dict[str, Any]:
        safe, truncated = truncate_dict_to_token_limit(
            payload, settings.GROQ_MODEL, settings.LLM_MAX_INPUT_TOKENS
        )
        if truncated:
            logger.warning("groq.payload.truncated", task_name=task_name)
        return safe

    def _azure_fallback(self):
        """
        Lazily create an AzureOpenAIClient for fallback use.
        Returns None if AZURE_OPENAI_API_KEY is not configured.
        """
        if not settings.AZURE_OPENAI_API_KEY:
            return None
        try:
            from app.ai.azure_openai_client import AzureOpenAIClient
            return AzureOpenAIClient()
        except Exception as exc:
            logger.warning("groq_fallback.azure_init_failed", error=str(exc))
            return None

    # ── Sync interface ────────────────────────────────────────────────────────

    def classify_api_call(
        self, payload: dict, db: Optional[Session] = None
    ) -> ClassificationResponse:
        system_prompt = (
            "You are an API traffic classification engine.\n"
            "Decide if an HTTP call is a business API; reject telemetry, "
            "tracking, and static assets.\n"
            "Classify business domain and action if applicable.\n"
            "Return strict JSON only."
        )
        augmented = self._inject_schema(system_prompt, _CLASSIFY_SCHEMA)
        safe_payload = self._truncate(payload, "har_classification")

        try:
            response = self._sync.chat.completions.create(
                model=settings.GROQ_MODEL,
                max_tokens=settings.LLM_MAX_COMPLETION_TOKENS,
                messages=[
                    {"role": "system", "content": augmented},
                    {"role": "user", "content": json.dumps(safe_payload, ensure_ascii=False)},
                ],
                response_format={"type": "json_object"},
            )
            self._log_usage(db, "har_classification", response.usage)
            raw = json.loads(response.choices[0].message.content)
            return ClassificationResponse.parse_llm_response(raw, ClassificationResponse.fallback())

        except (RateLimitError, APIError, APITimeoutError) as groq_exc:
            logger.warning(
                "groq_fallback_to_azure",
                method="classify_api_call",
                error=str(groq_exc),
            )
            azure = self._azure_fallback()
            if azure is None:
                raise
            return azure.classify_api_call(payload, db)

    def structured_chat(
        self,
        system_prompt: str,
        user_payload: dict[str, Any],
        json_schema: dict[str, Any],
        task_name: str = "unknown",
        db: Optional[Session] = None,
    ) -> dict[str, Any]:
        augmented = self._inject_schema(system_prompt, json_schema)
        safe_payload = self._truncate(user_payload, task_name)

        try:
            response = self._sync.chat.completions.create(
                model=settings.GROQ_MODEL,
                max_tokens=settings.LLM_MAX_COMPLETION_TOKENS,
                messages=[
                    {"role": "system", "content": augmented},
                    {"role": "user", "content": json.dumps(safe_payload, ensure_ascii=False)},
                ],
                response_format={"type": "json_object"},
            )
            self._log_usage(db, task_name, response.usage)
            raw = json.loads(response.choices[0].message.content)
            if not isinstance(raw, dict):
                logger.warning("groq.structured_chat.non_dict", task_name=task_name)
                return {}
            return raw

        except (RateLimitError, APIError, APITimeoutError) as groq_exc:
            logger.warning(
                "groq_fallback_to_azure",
                method="structured_chat",
                task_name=task_name,
                error=str(groq_exc),
            )
            azure = self._azure_fallback()
            if azure is None:
                raise
            return azure.structured_chat(system_prompt, user_payload, json_schema, task_name, db)

    # ── Async interface ───────────────────────────────────────────────────────

    async def structured_chat_async(
        self,
        system_prompt: str,
        user_payload: dict[str, Any],
        json_schema: dict[str, Any],
        task_name: str = "unknown",
        db: Optional[Session] = None,
    ) -> dict[str, Any]:
        augmented = self._inject_schema(system_prompt, json_schema)
        safe_payload = self._truncate(user_payload, task_name)

        try:
            response = await self._async.chat.completions.create(
                model=settings.GROQ_MODEL,
                max_tokens=settings.LLM_MAX_COMPLETION_TOKENS,
                messages=[
                    {"role": "system", "content": augmented},
                    {"role": "user", "content": json.dumps(safe_payload, ensure_ascii=False)},
                ],
                response_format={"type": "json_object"},
            )
            self._log_usage(db, task_name, response.usage)
            raw = json.loads(response.choices[0].message.content)
            if not isinstance(raw, dict):
                logger.warning("groq.structured_chat_async.non_dict", task_name=task_name)
                return {}
            return raw

        except (RateLimitError, APIError, APITimeoutError) as groq_exc:
            logger.warning(
                "groq_fallback_to_azure",
                method="structured_chat_async",
                task_name=task_name,
                error=str(groq_exc),
            )
            azure = self._azure_fallback()
            if azure is None:
                raise
            return await azure.structured_chat_async(
                system_prompt, user_payload, json_schema, task_name, db
            )
