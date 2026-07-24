"""
LLM observability service — persists call records and reports daily usage.

Fix 14.2: request_id is read from the current ContextVar and stored with
each LLM call so every Azure OpenAI call can be traced back to the HTTP
request that triggered it (even through Celery task chains).

Fix 14.3: print() replaced with structlog.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.context import current_request_id
from app.core.logging import get_logger
from app.llm_observability.cost_estimator import active_model, estimate_llm_cost, is_high_token_call
from app.llm_observability.repository import (
    create_llm_call,
    get_overall_summary,
    get_today_token_summary,
)
from app.llm_observability.terminal_reporter import log_ai_usage

logger = get_logger(__name__)


def log_llm_call_and_print_terminal_summary(
    db: Session,
    task_name: str,
    prompt_tokens: int,
    completion_tokens: int,
    celery_task_id: str | None = None,
    estimated_prompt_tokens: int | None = None,
) -> None:
    """Persist an LLM call record and emit a daily usage summary log line."""
    total_tokens = prompt_tokens + completion_tokens
    model = active_model()
    cost = estimate_llm_cost(prompt_tokens, completion_tokens, model=model)
    high = is_high_token_call(total_tokens)
    request_id = current_request_id.get()

    call = create_llm_call(
        db=db,
        task_name=task_name,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        estimated_cost_usd=cost,
        is_high_token=high,
        request_id=request_id,
        celery_task_id=celery_task_id,
        estimated_prompt_tokens=estimated_prompt_tokens,
    )

    logger.info(
        "llm_call.recorded",
        task_name=task_name,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        estimated_cost_usd=cost,
        is_high_token=high,
        request_id=request_id,
        celery_task_id=celery_task_id,
    )

    try:
        from app.observability.metrics import record_llm_tokens
        record_llm_tokens(
            task_name=task_name,
            model_name=model,
            total_tokens=total_tokens,
            estimated_cost=call.estimated_cost_usd,
            provider=settings.AI_PROVIDER,
        )
    except Exception:
        pass

    summary = get_today_token_summary(db)
    log_ai_usage(
        tokens_today=summary["tokens_today"],
        cost_today=summary["cost_today"],
        high_token_calls=summary["high_token_calls"],
    )


def print_current_ai_usage_today(db: Session) -> None:
    """Emit current-day token usage as a structured log line."""
    summary = get_today_token_summary(db)
    log_ai_usage(
        tokens_today=summary["tokens_today"],
        cost_today=summary["cost_today"],
        high_token_calls=summary["high_token_calls"],
    )


def get_model_cost_comparison(db: Session) -> dict:
    """
    Project lifetime token usage onto every priced model (current Groq
    model vs. the Bedrock Claude Haiku/Sonnet/Opus candidates) so you can
    compare "what we're actually spending" against "what we'd spend on
    model X" using real volume instead of guessing. Cheapest model first.
    """
    from app.llm_observability.pricing import compare_models

    lifetime = get_overall_summary(db)
    projected = compare_models(
        prompt_tokens=lifetime["total_prompt_tokens"],
        completion_tokens=lifetime["total_completion_tokens"],
    )
    current = active_model()

    return {
        "based_on": {
            "total_calls": lifetime["total_calls"],
            "total_prompt_tokens": lifetime["total_prompt_tokens"],
            "total_completion_tokens": lifetime["total_completion_tokens"],
        },
        "current_provider": settings.AI_PROVIDER,
        "current_model": current,
        "current_actual_cost_usd": lifetime["total_cost_usd"],
        "projected_by_model": projected,
    }
