from sqlalchemy.orm import Session

from app.core.config import settings
from app.llm_observability.cost_estimator import estimate_llm_cost, is_high_token_call
from app.llm_observability.repository import create_llm_call, get_today_token_summary
from app.llm_observability.terminal_reporter import print_ai_usage


def log_llm_call_and_print_terminal_summary(
    db: Session,
    task_name: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> None:
    total_tokens = prompt_tokens + completion_tokens
    cost = estimate_llm_cost(prompt_tokens, completion_tokens)
    high = is_high_token_call(total_tokens)

    call = create_llm_call(
        db=db,
        task_name=task_name,
        model=settings.AZURE_OPENAI_MODEL,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        estimated_cost_usd=cost,
        is_high_token=high,
    )

    try:
        from app.observability.metrics import record_llm_tokens
        record_llm_tokens(
            task_name=task_name,
            model_name=settings.AZURE_OPENAI_MODEL,
            total_tokens=total_tokens,
            estimated_cost=call.estimated_cost_usd,
        )
    except Exception:
        pass

    summary = get_today_token_summary(db)
    print_ai_usage(
        tokens_today=summary["tokens_today"],
        cost_today=summary["cost_today"],
        high_token_calls=summary["high_token_calls"],
    )


def print_current_ai_usage_today(db: Session) -> None:
    summary = get_today_token_summary(db)
    print_ai_usage(
        tokens_today=summary["tokens_today"],
        cost_today=summary["cost_today"],
        high_token_calls=summary["high_token_calls"],
    )
