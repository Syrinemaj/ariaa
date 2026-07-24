from __future__ import annotations

from typing import Optional

from app.core.config import settings
from app.llm_observability.pricing import estimate_cost as _priced_estimate


def active_model() -> str:
    """Model name for the currently configured provider (settings.AI_PROVIDER)."""
    if settings.AI_PROVIDER == "groq":
        return settings.GROQ_MODEL
    return settings.AZURE_OPENAI_MODEL


def estimate_llm_cost(
    prompt_tokens: int,
    completion_tokens: int,
    model: Optional[str] = None,
) -> float:
    """
    Cost of a call, priced by the model that actually served it.

    Previously this always applied settings.LLM_PROMPT_COST_PER_1K /
    LLM_COMPLETION_COST_PER_1K, which are Azure gpt-4o-mini rates — correct
    for Azure calls, silently wrong for Groq calls (AI_PROVIDER=groq is the
    default). `model` defaults to whichever provider/model is currently
    configured; pass it explicitly to price a call made against a different
    model (e.g. judge.py's Azure fallback while AI_PROVIDER=groq).
    """
    target = model or active_model()
    try:
        return _priced_estimate(prompt_tokens, completion_tokens, target)
    except KeyError:
        # No pricing entry for this model (e.g. a custom Azure deployment
        # name) — fall back to the configured generic rate instead of
        # raising mid-request.
        prompt_cost = (prompt_tokens / 1000) * settings.LLM_PROMPT_COST_PER_1K
        completion_cost = (completion_tokens / 1000) * settings.LLM_COMPLETION_COST_PER_1K
        return round(prompt_cost + completion_cost, 6)


def is_high_token_call(total_tokens: int) -> bool:
    return total_tokens >= settings.LLM_HIGH_TOKEN_THRESHOLD
