"""ARIA — Amazon Bedrock client (Converse API via boto3). Seul client de
complétion du projet — GroqClient et AzureOpenAIClient ont été supprimés
après l'évaluation de sélection de modèle (evaluation/aggregate.py).

Réécrit depuis une première version basée sur AnthropicBedrockMantle (SDK
Anthropic) : Mantle retournait systématiquement 404 "model does not exist"
sur ce compte, pour tous les formats d'ID testés — alors que
boto3 bedrock-runtime.converse() avec exactement les mêmes IDs et
credentials fonctionne (vérifié empiriquement). Converse est aussi une API
Bedrock générique, pas spécifique à Anthropic : ce même client sert Amazon
Nova, Meta Llama, DeepSeek, etc. en changeant juste `model` — pas besoin
d'un second client dédié par famille de modèle.

La sortie structurée passe par `toolConfig` avec un `toolChoice` forcé sur
l'unique tool défini par `json_schema` — c'est le mécanisme standard de
Converse pour obtenir un JSON garanti-conforme, pas un "mode JSON" séparé
nécessitant une injection de schéma dans le prompt.

Promoted to a full AIClientProtocol implementation (classify_api_call,
truncation, retry, real-usage cost logging) when AI_PROVIDER=bedrock became
the production default. Originally deepseek.v3.2 (chosen after
evaluation/run_scripts/run_param_detection_eval.py, a single-task
comparison); replaced by amazon.nova-lite-v1:0 after a full 8-task
comparison across every real LLM call site — statistically tied on quality,
~37x cheaper, ~2.4x faster with far more consistent latency (see
config.py::BEDROCK_MODEL and evaluation/results/full_comparison.csv).
Reasoning models on this provider (deepseek.v3.2 observed directly) can
spend part of max_tokens on internal reasoning before emitting the tool
call — if it runs out first, Converse returns no toolUse block at all
rather than a malformed one; this is part of why it lost the comparison
(highly variable latency, occasional truncation). structured_chat retries
once with an explicit nudge, then raises StructuredResponseError — this
retry path matters less for the current default (amazon.nova-lite-v1:0 is
not a reasoning model) but is kept as a general safety net for any Bedrock
model behind this client, reasoning or not.

Nécessite des credentials AWS résolus classiquement par boto3 (env vars /
~/.aws/credentials / IAM role) — jamais codés en dur ici. Si l'horloge
système locale dérive (SigV4 rejeté), voir evaluation/tracer/_clock_fix.py
— ce module-ci n'a aucune dépendance dessus, la correction se fait en amont
côté appelant.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

import boto3
from sqlalchemy.orm import Session

from app.ai.base_client import StructuredResponseError
from app.ai.response_schemas import ClassificationResponse
from app.ai.token_counter import truncate_dict_to_token_limit
from app.ai.traffic_classification import CLASSIFY_SCHEMA as _CLASSIFY_SCHEMA
from app.ai.traffic_classification import SYSTEM_PROMPT as _CLASSIFY_SYSTEM_PROMPT
from app.core.config import settings

logger = logging.getLogger(__name__)

# Default completion budget — 1500 was sized for deepseek.v3.2's reasoning
# overhead (~1200 empirically required to reliably reach its tool call, see
# evaluation/run_scripts/run_param_detection_eval.py: 56% completion at 300
# tokens, 100% at 1200 on the same 16-case sample). Now more headroom than
# amazon.nova-lite-v1:0 (the current default, not a reasoning model) needs,
# but kept at 1500 rather than tightened: this client is shared by any
# Bedrock model passed to it, including reasoning ones, and the cost of
# unused headroom is far lower than the cost of truncation.
_DEFAULT_MAX_TOKENS = 1500


def _pricing_key_for(model_id: str) -> str:
    """PRICING (app/llm_observability/pricing.py) is keyed by the bare
    model id — some Bedrock inference profiles need a region/scope prefix
    ("eu.", "global.", "us.") for the actual API call that isn't part of
    the pricing lookup key. Strip it ONLY for cost estimation, never for
    the real converse() call. No-op for models with no such prefix (e.g.
    "deepseek.v3.2", the production default)."""
    for prefix in ("eu.", "global.", "us."):
        if model_id.startswith(prefix):
            return model_id[len(prefix):]
    return model_id


class BedrockClient:
    """Structurellement compatible AIClientProtocol — backend Bedrock
    Converse, fonctionne avec n'importe quel modèle Bedrock (Anthropic,
    Amazon Nova, DeepSeek, ...), pas seulement Claude."""

    def __init__(self, model: str, aws_region: Optional[str] = None) -> None:
        self._client = boto3.client("bedrock-runtime", region_name=aws_region or settings.AWS_REGION)
        self.model = model

    # ── Sync interface ────────────────────────────────────────────────────────

    def classify_api_call(self, payload: dict, db: Optional[Session] = None) -> ClassificationResponse:
        safe_payload, truncated = truncate_dict_to_token_limit(
            payload, self.model, settings.LLM_MAX_INPUT_TOKENS
        )
        if truncated:
            logger.warning("bedrock.classify_api_call: payload truncated to fit token limit")

        raw = self.structured_chat(
            system_prompt=_CLASSIFY_SYSTEM_PROMPT,
            user_payload=safe_payload,
            json_schema=_CLASSIFY_SCHEMA,
            task_name="har_classification",
            db=db,
        )
        return ClassificationResponse.parse_llm_response(raw, ClassificationResponse.fallback())

    def structured_chat(
        self,
        system_prompt: str,
        user_payload: dict[str, Any],
        json_schema: dict[str, Any],
        task_name: str,
        db: Optional[Session] = None,
        model: Optional[str] = None,
        max_tokens: int = _DEFAULT_MAX_TOKENS,
    ) -> dict[str, Any]:
        target_model = model or self.model
        safe_payload, truncated = truncate_dict_to_token_limit(
            user_payload, target_model, settings.LLM_MAX_INPUT_TOKENS
        )
        if truncated:
            logger.warning("bedrock.structured_chat[%s]: payload truncated to fit token limit", task_name)

        tool_name = json_schema.get("name") or "extract"
        tool_config = {
            "tools": [{
                "toolSpec": {
                    "name": tool_name,
                    "description": f"Structured output for task '{task_name}'",
                    "inputSchema": {"json": json_schema["schema"]},
                }
            }],
            "toolChoice": {"tool": {"name": tool_name}},
        }

        correction: Optional[str] = None
        for attempt in range(2):
            content = [{"text": json.dumps(safe_payload, ensure_ascii=False)}]
            if correction:
                content.append({"text": correction})

            response = self._client.converse(
                modelId=target_model,
                system=[{"text": system_prompt}],
                messages=[{"role": "user", "content": content}],
                # settings.LLM_STRUCTURED_TEMPERATURE — was missing here, so
                # this provider sampled at the model's own default temperature
                # (well above 0.15) on every classification/enrichment call,
                # producing different endpoint counts and business_domain
                # wording run over run on the exact same HAR.
                inferenceConfig={"maxTokens": max_tokens, "temperature": settings.LLM_STRUCTURED_TEMPERATURE},
                toolConfig=tool_config,
            )
            self._log_usage(db, task_name, response.get("usage") or {}, target_model)

            for block in response["output"]["message"]["content"]:
                if "toolUse" in block:
                    return block["toolUse"]["input"]

            correction = (
                f"Your previous response did not call the required tool {tool_name!r}. "
                "You MUST respond by calling that tool with the structured output — "
                "no plain text, no explanation, call the tool directly."
            )
            logger.warning(
                "bedrock.structured_chat.no_tool_use",
                extra={"task_name": task_name, "model": target_model, "attempt": attempt},
            )

        raise StructuredResponseError(
            f"Bedrock model {target_model!r} never called the required tool for task "
            f"{task_name!r} after retry — likely ran out of max_tokens on internal "
            f"reasoning before reaching the tool call (current cap: {max_tokens})."
        )

    # ── Async interface ───────────────────────────────────────────────────────

    async def structured_chat_async(
        self,
        system_prompt: str,
        user_payload: dict[str, Any],
        json_schema: dict[str, Any],
        task_name: str,
        db: Optional[Session] = None,
        max_tokens: int = _DEFAULT_MAX_TOKENS,
    ) -> dict[str, Any]:
        return await asyncio.to_thread(
            self.structured_chat, system_prompt, user_payload, json_schema, task_name, db, None, max_tokens,
        )

    # ── Internal helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _log_usage(db: Optional[Session], task_name: str, usage: dict, model: str) -> None:
        """Converse returns usage as a plain dict with inputTokens/
        outputTokens — real billed counts, not the tiktoken estimate
        evaluation/tracer/normalization_tracer.py has to fall back to when
        it can't see raw API usage."""
        prompt_tokens = usage.get("inputTokens")
        completion_tokens = usage.get("outputTokens")
        if prompt_tokens is None or completion_tokens is None:
            return

        pricing_model = _pricing_key_for(model)

        if db is not None:
            # log_llm_call_and_print_terminal_summary already records to
            # Prometheus (with correctly-priced cost) as part of persisting
            # the call — do not also record here, or every call with a db
            # session double-counts aria_llm_tokens_total / aria_llm_cost_total.
            from app.llm_observability.service import log_llm_call_and_print_terminal_summary
            log_llm_call_and_print_terminal_summary(
                db=db, task_name=task_name,
                prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
            )
            return

        # ARIA-OBS-FIX: most callers (planner, normalization...) never pass
        # a db session since
        # structured_chat() is sync and the caller's session is often async.
        # Open a short-lived sync session so the call is persisted to
        # llm_calls (not just an in-process Prometheus counter that resets
        # on every restart) with zero change required at any call site.
        try:
            from app.db.session import SessionLocal
            from app.llm_observability.service import log_llm_call_and_print_terminal_summary
            session = SessionLocal()
            try:
                log_llm_call_and_print_terminal_summary(
                    db=session, task_name=task_name,
                    prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
                )
                session.commit()
            finally:
                session.close()
        except Exception:
            pass
