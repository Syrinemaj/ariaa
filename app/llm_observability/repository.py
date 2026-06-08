"""
LLM call persistence — stores cost/token records with full correlation context.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import func, text
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
    request_id: Optional[str] = None,
    celery_task_id: Optional[str] = None,
    estimated_prompt_tokens: Optional[int] = None,
) -> LLMCall:
    """Persist an LLM call record with optional correlation identifiers."""
    record = LLMCall(
        task_name=task_name,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        estimated_cost_usd=estimated_cost_usd,
        is_high_token=is_high_token,
        request_id=request_id,
        celery_task_id=celery_task_id,
        estimated_prompt_tokens=estimated_prompt_tokens,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_today_token_summary(db: Session) -> dict:
    """Return total tokens, cost, and high-token call count for today (UTC)."""
    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

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


# ── Benchmark queries ─────────────────────────────────────────────────────────

def get_benchmark_by_task(db: Session) -> list[dict[str, Any]]:
    """
    Per task_name: call count, avg/total tokens, avg cost, estimation accuracy.

    estimation_accuracy: ratio of estimated vs actual prompt tokens.
    1.0 = perfect estimate. >1.0 = over-estimated. <1.0 = under-estimated.
    NULL when no estimated_prompt_tokens rows exist for that task.
    """
    rows = (
        db.query(
            LLMCall.task_name,
            LLMCall.model,
            func.count(LLMCall.id).label("call_count"),
            func.avg(LLMCall.prompt_tokens).label("avg_prompt_tokens"),
            func.avg(LLMCall.completion_tokens).label("avg_completion_tokens"),
            func.avg(LLMCall.total_tokens).label("avg_total_tokens"),
            func.sum(LLMCall.total_tokens).label("total_tokens"),
            func.avg(LLMCall.estimated_cost_usd).label("avg_cost_usd"),
            func.sum(LLMCall.estimated_cost_usd).label("total_cost_usd"),
            func.max(LLMCall.total_tokens).label("max_total_tokens"),
            func.count(LLMCall.id).filter(LLMCall.is_high_token.is_(True)).label("high_token_count"),
            func.avg(LLMCall.estimated_prompt_tokens).label("avg_estimated_prompt_tokens"),
        )
        .group_by(LLMCall.task_name, LLMCall.model)
        .order_by(func.sum(LLMCall.total_tokens).desc())
        .all()
    )

    result = []
    for row in rows:
        avg_actual = float(row.avg_prompt_tokens or 0)
        avg_estimated = float(row.avg_estimated_prompt_tokens or 0)

        accuracy: float | None = None
        delta_tokens: int | None = None
        if avg_estimated > 0 and avg_actual > 0:
            accuracy = round(avg_estimated / avg_actual, 3)
            delta_tokens = round(avg_estimated - avg_actual)

        result.append({
            "task_name":                  row.task_name,
            "model":                      row.model,
            "call_count":                 int(row.call_count),
            "avg_prompt_tokens":          round(float(row.avg_prompt_tokens or 0)),
            "avg_completion_tokens":      round(float(row.avg_completion_tokens or 0)),
            "avg_total_tokens":           round(float(row.avg_total_tokens or 0)),
            "total_tokens":               int(row.total_tokens or 0),
            "avg_cost_usd":               round(float(row.avg_cost_usd or 0), 6),
            "total_cost_usd":             round(float(row.total_cost_usd or 0), 6),
            "max_total_tokens":           int(row.max_total_tokens or 0),
            "high_token_count":           int(row.high_token_count),
            "avg_estimated_prompt_tokens": round(avg_estimated) if avg_estimated else None,
            "estimation_accuracy":        accuracy,
            "avg_estimation_delta_tokens": delta_tokens,
        })
    return result


def get_benchmark_over_time(
    db: Session,
    days: int = 30,
) -> list[dict[str, Any]]:
    """
    Daily aggregates for the last `days` days.
    Returns one row per day: date, total_tokens, total_cost, call_count.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)

    rows = (
        db.query(
            func.date(LLMCall.called_at).label("day"),
            func.count(LLMCall.id).label("call_count"),
            func.sum(LLMCall.total_tokens).label("total_tokens"),
            func.sum(LLMCall.prompt_tokens).label("total_prompt_tokens"),
            func.sum(LLMCall.completion_tokens).label("total_completion_tokens"),
            func.sum(LLMCall.estimated_cost_usd).label("total_cost_usd"),
            func.count(LLMCall.id).filter(LLMCall.is_high_token.is_(True)).label("high_token_calls"),
        )
        .filter(LLMCall.called_at >= since)
        .group_by(func.date(LLMCall.called_at))
        .order_by(func.date(LLMCall.called_at))
        .all()
    )

    return [
        {
            "day":                    str(row.day),
            "call_count":             int(row.call_count),
            "total_tokens":           int(row.total_tokens or 0),
            "total_prompt_tokens":    int(row.total_prompt_tokens or 0),
            "total_completion_tokens": int(row.total_completion_tokens or 0),
            "total_cost_usd":         round(float(row.total_cost_usd or 0), 6),
            "high_token_calls":       int(row.high_token_calls),
        }
        for row in rows
    ]


def get_high_token_calls(
    db: Session,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Most expensive individual LLM calls (total_tokens DESC)."""
    rows = (
        db.query(LLMCall)
        .filter(LLMCall.is_high_token.is_(True))
        .order_by(LLMCall.total_tokens.desc())
        .limit(limit)
        .all()
    )
    return [_call_to_dict(r) for r in rows]


def get_recent_calls(
    db: Session,
    limit: int = 100,
    task_name: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Recent LLM calls, optionally filtered by task_name."""
    q = db.query(LLMCall).order_by(LLMCall.called_at.desc())
    if task_name:
        q = q.filter(LLMCall.task_name == task_name)
    rows = q.limit(limit).all()
    return [_call_to_dict(r) for r in rows]


def get_overall_summary(db: Session) -> dict[str, Any]:
    """Lifetime totals — all time, not just today."""
    result = (
        db.query(
            func.count(LLMCall.id).label("total_calls"),
            func.coalesce(func.sum(LLMCall.prompt_tokens), 0).label("total_prompt_tokens"),
            func.coalesce(func.sum(LLMCall.completion_tokens), 0).label("total_completion_tokens"),
            func.coalesce(func.sum(LLMCall.total_tokens), 0).label("total_tokens"),
            func.coalesce(func.sum(LLMCall.estimated_cost_usd), 0.0).label("total_cost_usd"),
            func.count(LLMCall.id).filter(LLMCall.is_high_token.is_(True)).label("high_token_calls"),
            func.avg(LLMCall.total_tokens).label("avg_tokens_per_call"),
        )
        .one()
    )
    return {
        "total_calls":             int(result.total_calls),
        "total_prompt_tokens":     int(result.total_prompt_tokens),
        "total_completion_tokens": int(result.total_completion_tokens),
        "total_tokens":            int(result.total_tokens),
        "total_cost_usd":          round(float(result.total_cost_usd), 4),
        "high_token_calls":        int(result.high_token_calls),
        "avg_tokens_per_call":     round(float(result.avg_tokens_per_call or 0)),
    }


def _call_to_dict(call: LLMCall) -> dict[str, Any]:
    return {
        "id":                       call.id,
        "task_name":                call.task_name,
        "model":                    call.model,
        "prompt_tokens":            call.prompt_tokens,
        "completion_tokens":        call.completion_tokens,
        "total_tokens":             call.total_tokens,
        "estimated_cost_usd":       call.estimated_cost_usd,
        "is_high_token":            call.is_high_token,
        "estimated_prompt_tokens":  call.estimated_prompt_tokens,
        "estimation_delta":         (
            call.estimated_prompt_tokens - call.prompt_tokens
            if call.estimated_prompt_tokens is not None else None
        ),
        "request_id":               call.request_id,
        "celery_task_id":           call.celery_task_id,
        "called_at":                call.called_at.isoformat(),
    }
