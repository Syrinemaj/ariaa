"""
GroqClient — primary LLM completion provider.

Uses the openai SDK pointed at Groq's OpenAI-compatible endpoint
(no extra package required beyond openai>=1.42.0).

Fallback chain
--------------
If Groq raises RateLimitError, APIError, or APITimeoutError, the client
retries, in order:
  1. GROQ_API_KEY_2 — a second Groq account/key, when configured. This is
     tried first because Groq's free tier rate-limits per key (tokens per
     day), so a second key routes around exactly that failure mode.
  2. GROQ_API_KEY_3 — a third Groq account/key, when configured.
No external provider fallback (e.g. Azure) is attempted — if all
configured Groq keys fail, the original Groq exception is re-raised.

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

from app.ai.base_client import StructuredResponseError
from app.ai.response_schemas import ClassificationResponse
from app.ai.token_counter import truncate_dict_to_token_limit
from app.ai.traffic_classification import CLASSIFY_SCHEMA as _CLASSIFY_SCHEMA
from app.ai.traffic_classification import SYSTEM_PROMPT as _CLASSIFY_SYSTEM_PROMPT
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"


class GroqClient:
    """
    Groq LLM client — primary provider for all completions.
    Assign to app.state.ai_client in the FastAPI lifespan (see main.py).
    """

    def __init__(self, api_key: Optional[str] = None) -> None:
        common = {"api_key": api_key or settings.GROQ_API_KEY, "base_url": _GROQ_BASE_URL}
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
                usage.prompt_tokens or 0, usage.completion_tokens or 0, model=settings.GROQ_MODEL
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

    def _truncate(self, payload: dict[str, Any], task_name: str) -> dict[str, Any]:
        safe, truncated = truncate_dict_to_token_limit(
            payload, settings.GROQ_MODEL, settings.LLM_MAX_INPUT_TOKENS
        )
        if truncated:
            logger.warning("groq.payload.truncated", task_name=task_name)
        return safe

    def _secondary_groq_fallback(self) -> Optional["GroqClient"]:
        """
        Lazily create a second GroqClient using GROQ_API_KEY_2 — a distinct
        Groq account/key to route around this key's rate limit. Returns
        None if not configured, or if it's the same key as the primary
        (would just fail the same way).
        """
        if not settings.GROQ_API_KEY_2 or settings.GROQ_API_KEY_2 == settings.GROQ_API_KEY:
            return None
        try:
            return GroqClient(api_key=settings.GROQ_API_KEY_2)
        except Exception as exc:
            logger.warning("groq_fallback.secondary_key_init_failed", error=str(exc))
            return None

    def _tertiary_groq_fallback(self) -> Optional["GroqClient"]:
        """
        Lazily create a third GroqClient using GROQ_API_KEY_3 — tried after
        the secondary key also hits its rate limit. Returns None if not
        configured, or if it duplicates a key already tried (primary or
        secondary — would just fail the same way).
        """
        if not settings.GROQ_API_KEY_3 or settings.GROQ_API_KEY_3 in (
            settings.GROQ_API_KEY, settings.GROQ_API_KEY_2,
        ):
            return None
        try:
            return GroqClient(api_key=settings.GROQ_API_KEY_3)
        except Exception as exc:
            logger.warning("groq_fallback.tertiary_key_init_failed", error=str(exc))
            return None

    # ── Sync interface ────────────────────────────────────────────────────────

    def classify_api_call(
        self, payload: dict, db: Optional[Session] = None
    ) -> ClassificationResponse:
        augmented = self._inject_schema(_CLASSIFY_SYSTEM_PROMPT, _CLASSIFY_SCHEMA)
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
                "groq_fallback_to_secondary_key",
                method="classify_api_call",
                error=str(groq_exc),
            )
            secondary = self._secondary_groq_fallback()
            if secondary is not None:
                try:
                    return secondary.classify_api_call(payload, db)
                except (RateLimitError, APIError, APITimeoutError) as secondary_exc:
                    logger.warning(
                        "groq_secondary_key_failed",
                        method="classify_api_call",
                        error=str(secondary_exc),
                    )

            logger.warning(
                "groq_fallback_to_tertiary_key",
                method="classify_api_call",
                error=str(groq_exc),
            )
            tertiary = self._tertiary_groq_fallback()
            if tertiary is not None:
                try:
                    return tertiary.classify_api_call(payload, db)
                except (RateLimitError, APIError, APITimeoutError) as tertiary_exc:
                    logger.warning(
                        "groq_tertiary_key_failed",
                        method="classify_api_call",
                        error=str(tertiary_exc),
                    )

            # All configured Groq keys exhausted — no external fallback.
            raise

    @staticmethod
    def _non_nullable_required_fields(json_schema: dict[str, Any]) -> list[str]:
        """
        Fields that are both required AND whose declared type does not
        include "null" — e.g. business_intent's "action" (string) vs
        "business_domain" (["string", "null"]), which IS allowed to be null.
        Groq's json_object mode is best-effort schema compliance, so a
        required field can come back present-but-null; a plain "is it
        missing" check wouldn't catch that.
        """
        schema_body = json_schema.get("schema", json_schema)
        required = schema_body.get("required", [])
        properties = schema_body.get("properties", {})
        non_nullable = []
        for field in required:
            field_type = properties.get(field, {}).get("type")
            types = field_type if isinstance(field_type, list) else [field_type]
            if "null" not in types:
                non_nullable.append(field)
        return non_nullable

    def structured_chat(
        self,
        system_prompt: str,
        user_payload: dict[str, Any],
        json_schema: dict[str, Any],
        task_name: str = "unknown",
        db: Optional[Session] = None,
        # ARIA-EVAL: optional per-call override of settings.GROQ_MODEL.
        # Added so evaluation/judge.py can request a model independent of
        # the pipeline's own (llama-3.3-70b-versatile) while still going
        # through the exact same primary->secondary->tertiary key cascade
        # below, instead of judge.py needing its own separate fallback
        # implementation. None (the default) preserves the exact previous
        # behaviour for every existing caller (intent_analyzer.py,
        # plan_generator.py, ...) — none of them pass this.
        model: Optional[str] = None,
    ) -> dict[str, Any]:
        augmented = self._inject_schema(system_prompt, json_schema)
        safe_payload = self._truncate(user_payload, task_name)
        required = json_schema.get("schema", json_schema).get("required", [])
        non_nullable = self._non_nullable_required_fields(json_schema)

        try:
            return self._structured_chat_with_retry(
                augmented=augmented, payload=safe_payload,
                required=required, non_nullable=non_nullable, task_name=task_name, db=db,
                model=model,
            )
        except (RateLimitError, APIError, APITimeoutError) as groq_exc:
            logger.warning(
                "groq_fallback_to_secondary_key",
                method="structured_chat",
                task_name=task_name,
                error=str(groq_exc),
            )
            secondary = self._secondary_groq_fallback()
            if secondary is not None:
                try:
                    return secondary._structured_chat_with_retry(
                        augmented=augmented, payload=safe_payload,
                        required=required, non_nullable=non_nullable, task_name=task_name, db=db,
                        model=model,
                    )
                except (RateLimitError, APIError, APITimeoutError) as secondary_exc:
                    logger.warning(
                        "groq_secondary_key_failed",
                        method="structured_chat",
                        task_name=task_name,
                        error=str(secondary_exc),
                    )

            logger.warning(
                "groq_fallback_to_tertiary_key",
                method="structured_chat",
                task_name=task_name,
                error=str(groq_exc),
            )
            tertiary = self._tertiary_groq_fallback()
            if tertiary is not None:
                try:
                    return tertiary._structured_chat_with_retry(
                        augmented=augmented, payload=safe_payload,
                        required=required, non_nullable=non_nullable, task_name=task_name, db=db,
                        model=model,
                    )
                except (RateLimitError, APIError, APITimeoutError) as tertiary_exc:
                    logger.warning(
                        "groq_tertiary_key_failed",
                        method="structured_chat",
                        task_name=task_name,
                        error=str(tertiary_exc),
                    )

            # All configured Groq keys exhausted — no external fallback.
            raise

    def _structured_chat_with_retry(
        self,
        augmented: str,
        payload: dict[str, Any],
        required: list[str],
        non_nullable: list[str],
        task_name: str,
        db: Optional[Session],
        model: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Groq's json_object mode guarantees valid JSON syntax, not schema
        compliance (unlike Azure's json_schema strict mode) — the model can
        still omit required fields. Retry once with the validation error fed
        back before giving up, instead of letting callers hit a raw KeyError
        on a missing field.
        """
        correction: Optional[str] = None
        for attempt in range(2):
            messages = [
                {"role": "system", "content": augmented},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ]
            if correction:
                messages.append({"role": "user", "content": correction})

            response = self._sync.chat.completions.create(
                model=model or settings.GROQ_MODEL,
                max_tokens=settings.LLM_MAX_COMPLETION_TOKENS,
                temperature=settings.LLM_STRUCTURED_TEMPERATURE,
                messages=messages,
                response_format={"type": "json_object"},
            )
            self._log_usage(db, task_name, response.usage)

            try:
                raw = json.loads(response.choices[0].message.content)
            except json.JSONDecodeError as exc:
                correction = f"Your previous response was not valid JSON ({exc}). Return ONLY the corrected JSON object."
                logger.warning("groq.structured_chat.invalid_json", task_name=task_name, attempt=attempt)
                continue

            if not isinstance(raw, dict):
                correction = "Your previous response was not a JSON object. Return ONLY a valid JSON object matching the schema."
                logger.warning("groq.structured_chat.non_dict", task_name=task_name, attempt=attempt)
                continue

            missing = [f for f in required if f not in raw]
            nulled = [f for f in non_nullable if f in raw and raw[f] is None]
            if missing or nulled:
                correction = (
                    f"Your previous response was missing required fields {missing} "
                    f"or had null values for non-nullable fields {nulled}. "
                    "Return the complete corrected JSON object."
                )
                logger.warning(
                    "groq.structured_chat.invalid_fields",
                    task_name=task_name, attempt=attempt, missing=missing, nulled=nulled,
                )
                continue

            return raw

        raise StructuredResponseError(
            f"Groq returned an invalid structured response for task {task_name!r} after retry."
        )

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
        required = json_schema.get("schema", json_schema).get("required", [])
        non_nullable = self._non_nullable_required_fields(json_schema)

        try:
            return await self._structured_chat_with_retry_async(
                augmented=augmented, payload=safe_payload,
                required=required, non_nullable=non_nullable, task_name=task_name, db=db,
            )
        except (RateLimitError, APIError, APITimeoutError) as groq_exc:
            logger.warning(
                "groq_fallback_to_secondary_key",
                method="structured_chat_async",
                task_name=task_name,
                error=str(groq_exc),
            )
            secondary = self._secondary_groq_fallback()
            if secondary is not None:
                try:
                    return await secondary._structured_chat_with_retry_async(
                        augmented=augmented, payload=safe_payload,
                        required=required, non_nullable=non_nullable, task_name=task_name, db=db,
                    )
                except (RateLimitError, APIError, APITimeoutError) as secondary_exc:
                    logger.warning(
                        "groq_secondary_key_failed",
                        method="structured_chat_async",
                        task_name=task_name,
                        error=str(secondary_exc),
                    )

            logger.warning(
                "groq_fallback_to_tertiary_key",
                method="structured_chat_async",
                task_name=task_name,
                error=str(groq_exc),
            )
            tertiary = self._tertiary_groq_fallback()
            if tertiary is not None:
                try:
                    return await tertiary._structured_chat_with_retry_async(
                        augmented=augmented, payload=safe_payload,
                        required=required, non_nullable=non_nullable, task_name=task_name, db=db,
                    )
                except (RateLimitError, APIError, APITimeoutError) as tertiary_exc:
                    logger.warning(
                        "groq_tertiary_key_failed",
                        method="structured_chat_async",
                        task_name=task_name,
                        error=str(tertiary_exc),
                    )

            # All configured Groq keys exhausted — no external fallback.
            raise

    async def _structured_chat_with_retry_async(
        self,
        augmented: str,
        payload: dict[str, Any],
        required: list[str],
        non_nullable: list[str],
        task_name: str,
        db: Optional[Session],
    ) -> dict[str, Any]:
        correction: Optional[str] = None
        for attempt in range(2):
            messages = [
                {"role": "system", "content": augmented},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ]
            if correction:
                messages.append({"role": "user", "content": correction})

            response = await self._async.chat.completions.create(
                model=settings.GROQ_MODEL,
                max_tokens=settings.LLM_MAX_COMPLETION_TOKENS,
                temperature=settings.LLM_STRUCTURED_TEMPERATURE,
                messages=messages,
                response_format={"type": "json_object"},
            )
            self._log_usage(db, task_name, response.usage)

            try:
                raw = json.loads(response.choices[0].message.content)
            except json.JSONDecodeError as exc:
                correction = f"Your previous response was not valid JSON ({exc}). Return ONLY the corrected JSON object."
                logger.warning("groq.structured_chat_async.invalid_json", task_name=task_name, attempt=attempt)
                continue

            if not isinstance(raw, dict):
                correction = "Your previous response was not a JSON object. Return ONLY a valid JSON object matching the schema."
                logger.warning("groq.structured_chat_async.non_dict", task_name=task_name, attempt=attempt)
                continue

            missing = [f for f in required if f not in raw]
            nulled = [f for f in non_nullable if f in raw and raw[f] is None]
            if missing or nulled:
                correction = (
                    f"Your previous response was missing required fields {missing} "
                    f"or had null values for non-nullable fields {nulled}. "
                    "Return the complete corrected JSON object."
                )
                logger.warning(
                    "groq.structured_chat_async.invalid_fields",
                    task_name=task_name, attempt=attempt, missing=missing, nulled=nulled,
                )
                continue

            return raw

        raise StructuredResponseError(
            f"Groq returned an invalid structured response for task {task_name!r} after retry."
        )
