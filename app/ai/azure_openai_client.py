"""
AzureOpenAIClient — wraps both sync and async Azure OpenAI clients.

Lifecycle
---------
- FastAPI: a single instance is created in the lifespan hook and stored as
  app.state.ai_client.  Routes get it via Depends(get_ai_client).
  This avoids creating a new httpx connection pool on every request.

- Celery tasks: instantiate directly (AzureOpenAIClient()) — each worker
  process gets its own instance, which is correct and safe.

Async vs Sync
-------------
- async methods (create_embedding_async, structured_chat_async) use the
  AsyncAzureOpenAI client and must be awaited.
- sync methods (create_embedding, classify_api_call, structured_chat)
  use the AzureOpenAI sync client and are safe to call from Celery tasks.

Validation
----------
All LLM responses are validated against Pydantic models (response_schemas.py)
before being returned.  Hallucinated or malformed responses fall back to a
safe default rather than propagating bad data into the pipeline.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from openai import AsyncAzureOpenAI, AzureOpenAI
from sqlalchemy.orm import Session

from app.ai.response_schemas import ClassificationResponse
from app.ai.token_counter import truncate_dict_to_token_limit, truncate_to_token_limit
from app.ai.traffic_classification import CLASSIFY_SCHEMA as _CLASSIFY_SCHEMA
from app.ai.traffic_classification import SYSTEM_PROMPT as _CLASSIFY_SYSTEM_PROMPT
from app.core.config import settings

logger = logging.getLogger(__name__)


class AzureOpenAIClient:
    def __init__(self) -> None:
        common = {
            "api_key": settings.AZURE_OPENAI_API_KEY,
            "azure_endpoint": settings.AZURE_OPENAI_ENDPOINT,
            "api_version": settings.AZURE_OPENAI_API_VERSION,
        }
        self._sync = AzureOpenAI(**common)
        self._async = AsyncAzureOpenAI(**common)

    # ─── Sync interface (Celery tasks + sync FastAPI routes) ──────────────────

    def classify_api_call(self, payload: dict, db: Optional[Session] = None) -> ClassificationResponse:
        safe_payload, truncated = truncate_dict_to_token_limit(
            payload, settings.AZURE_OPENAI_MODEL, settings.LLM_MAX_INPUT_TOKENS
        )
        if truncated:
            logger.warning("classify_api_call: payload truncated to fit token limit")

        response = self._sync.chat.completions.create(
            model=settings.AZURE_OPENAI_MODEL,
            max_tokens=settings.LLM_MAX_COMPLETION_TOKENS,
            messages=[
                {"role": "system", "content": _CLASSIFY_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(safe_payload, ensure_ascii=False)},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": _CLASSIFY_SCHEMA,
            },
        )

        self._log_usage(db, "har_classification", response.usage)

        raw = json.loads(response.choices[0].message.content)
        return ClassificationResponse.parse_llm_response(raw, ClassificationResponse.fallback())

    def create_embedding(self, text: str) -> list[float]:
        truncated_text, was_truncated = truncate_to_token_limit(
            text, settings.AZURE_OPENAI_EMBEDDING_MODEL, max_tokens=8191
        )
        if was_truncated:
            logger.warning("create_embedding: text truncated to 8191 tokens")

        response = self._sync.embeddings.create(
            model=settings.AZURE_OPENAI_EMBEDDING_MODEL,
            input=truncated_text,
        )
        return response.data[0].embedding

    def structured_chat(
        self,
        system_prompt: str,
        user_payload: dict[str, Any],
        json_schema: dict[str, Any],
        task_name: str = "unknown",
        db: Optional[Session] = None,
    ) -> dict[str, Any]:
        safe_payload, truncated = truncate_dict_to_token_limit(
            user_payload, settings.AZURE_OPENAI_MODEL, settings.LLM_MAX_INPUT_TOKENS
        )
        if truncated:
            logger.warning("structured_chat[%s]: payload truncated to fit token limit", task_name)

        response = self._sync.chat.completions.create(
            model=settings.AZURE_OPENAI_MODEL,
            max_tokens=settings.LLM_MAX_COMPLETION_TOKENS,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(safe_payload, ensure_ascii=False)},
            ],
            response_format={"type": "json_schema", "json_schema": json_schema},
        )

        self._log_usage(db, task_name, response.usage)

        raw = json.loads(response.choices[0].message.content)
        if not isinstance(raw, dict):
            logger.warning("structured_chat[%s]: LLM returned non-dict — using empty fallback", task_name)
            return {}
        return raw

    # ─── Async interface (FastAPI async routes) ───────────────────────────────

    async def create_embedding_async(self, text: str) -> list[float]:
        truncated_text, was_truncated = truncate_to_token_limit(
            text, settings.AZURE_OPENAI_EMBEDDING_MODEL, max_tokens=8191
        )
        if was_truncated:
            logger.warning("create_embedding_async: text truncated to 8191 tokens")

        response = await self._async.embeddings.create(
            model=settings.AZURE_OPENAI_EMBEDDING_MODEL,
            input=truncated_text,
        )
        return response.data[0].embedding

    async def structured_chat_async(
        self,
        system_prompt: str,
        user_payload: dict[str, Any],
        json_schema: dict[str, Any],
        task_name: str = "unknown",
        db: Optional[Session] = None,
    ) -> dict[str, Any]:
        safe_payload, truncated = truncate_dict_to_token_limit(
            user_payload, settings.AZURE_OPENAI_MODEL, settings.LLM_MAX_INPUT_TOKENS
        )
        if truncated:
            logger.warning("structured_chat_async[%s]: payload truncated", task_name)

        response = await self._async.chat.completions.create(
            model=settings.AZURE_OPENAI_MODEL,
            max_tokens=settings.LLM_MAX_COMPLETION_TOKENS,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(safe_payload, ensure_ascii=False)},
            ],
            response_format={"type": "json_schema", "json_schema": json_schema},
        )

        self._log_usage(db, task_name, response.usage)

        raw = json.loads(response.choices[0].message.content)
        if not isinstance(raw, dict):
            logger.warning("structured_chat_async[%s]: LLM returned non-dict", task_name)
            return {}
        return raw

    # ─── Internal helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _log_usage(db: Optional[Session], task_name: str, usage) -> None:
        if usage is None:
            return

        if db is not None:
            # log_llm_call_and_print_terminal_summary already records to
            # Prometheus (with correctly-priced cost) as part of persisting
            # the call — do not also record here, or every call with a db
            # session double-counts aria_llm_tokens_total / aria_llm_cost_total.
            from app.llm_observability.service import log_llm_call_and_print_terminal_summary
            log_llm_call_and_print_terminal_summary(
                db=db,
                task_name=task_name,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
            )
            return

        # No DB session — this is the only place Prometheus gets recorded,
        # so do it here, priced by the model that actually served the call.
        try:
            from app.llm_observability.cost_estimator import estimate_llm_cost
            from app.observability.metrics import record_llm_tokens
            total = (usage.prompt_tokens or 0) + (usage.completion_tokens or 0)
            cost = estimate_llm_cost(
                usage.prompt_tokens or 0, usage.completion_tokens or 0, model=settings.AZURE_OPENAI_MODEL
            )
            record_llm_tokens(
                task_name=task_name,
                model_name=settings.AZURE_OPENAI_MODEL,
                total_tokens=total,
                estimated_cost=cost,
                provider="azure",
            )
        except Exception:
            pass


# ─── FastAPI dependency ───────────────────────────────────────────────────────

def get_ai_client(request) -> AzureOpenAIClient:
    """
    FastAPI dependency — returns the singleton stored on app.state.
    Raises RuntimeError if the lifespan hook forgot to initialise it.
    """
    client = getattr(request.app.state, "ai_client", None)
    if client is None:
        raise RuntimeError(
            "AzureOpenAIClient not initialised. "
            "Ensure app.state.ai_client is set in the lifespan hook."
        )
    return client
