from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.llm_call import LLMCall


def create_llm_call(
    db: Session,
    task_name: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    estimated_cost_usd: float,
    is_high_token: bool,
) -> LLMCall:
    record = LLMCall(
        task_name=task_name,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        estimated_cost_usd=estimated_cost_usd,
        is_high_token=is_high_token,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_today_token_summary(db: Session) -> dict:
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    result = (
        db.query(
            func.coalesce(func.sum(LLMCall.total_tokens), 0).label("tokens_today"),
            func.coalesce(func.sum(LLMCall.estimated_cost_usd), 0.0).label("cost_today"),
            func.count(LLMCall.id).filter(LLMCall.is_high_token.is_(True)).label("high_token_calls"),
        )
        .filter(LLMCall.called_at >= today_start)
        .one()
    )

    return {
        "tokens_today": int(result.tokens_today),
        "cost_today": float(result.cost_today),
        "high_token_calls": int(result.high_token_calls),
    }
