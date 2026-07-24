"""
LLM usage & benchmark endpoints.

GET  /llm/summary          — lifetime totals + today summary (admin)
GET  /llm/compare-models   — lifetime usage projected onto Groq/Bedrock-Claude pricing
GET  /llm/benchmark/tasks  — per-task aggregates with estimation accuracy
GET  /llm/benchmark/daily  — daily token/cost timeline (last N days)
GET  /llm/high-token       — most expensive individual calls
GET  /llm/calls            — recent calls log, filterable by task
POST /llm/estimate         — pre-execution token & cost estimate
"""
from __future__ import annotations

import json
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import require_admin, require_admin_or_operator
from app.db.session import get_sync_db
from app.llm_observability.repository import (
    get_benchmark_by_task,
    get_benchmark_over_time,
    get_high_token_calls,
    get_overall_summary,
    get_recent_calls,
    get_today_token_summary,
)
from app.llm_observability.service import get_model_cost_comparison
from app.llm_observability.token_estimator import estimate_har_tokens, estimate_run_cost
from app.models.user import User

router = APIRouter(prefix="/llm", tags=["LLM Benchmark"])


# ── Response models ───────────────────────────────────────────────────────────

class TaskBenchmark(BaseModel):
    task_name: str
    model: str
    call_count: int
    avg_prompt_tokens: int
    avg_completion_tokens: int
    avg_total_tokens: int
    total_tokens: int
    avg_cost_usd: float
    total_cost_usd: float
    max_total_tokens: int
    high_token_count: int
    avg_estimated_prompt_tokens: Optional[int]
    estimation_accuracy: Optional[float]
    avg_estimation_delta_tokens: Optional[int]


class DailyBenchmark(BaseModel):
    day: str
    call_count: int
    total_tokens: int
    total_prompt_tokens: int
    total_completion_tokens: int
    total_cost_usd: float
    high_token_calls: int


class LLMSummary(BaseModel):
    today: dict[str, Any]
    lifetime: dict[str, Any]


class EstimateRequest(BaseModel):
    instruction: str
    context_endpoints: List[dict[str, Any]] = []
    plan_steps: int = 0


class EstimateResponse(BaseModel):
    model: str
    phases: dict[str, Any]
    total_estimated_prompt_tokens: int
    total_estimated_completion_tokens: int
    total_estimated_tokens: int
    estimated_cost_usd: float
    is_high_token_estimate: bool


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/summary", response_model=LLMSummary)
def get_llm_summary(
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin),
):
    """Lifetime totals + today snapshot. Admin only (contains cost data)."""
    return {
        "today":    get_today_token_summary(db),
        "lifetime": get_overall_summary(db),
    }


@router.get("/compare-models")
def compare_models(
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin),
):
    """
    Project lifetime token usage onto every priced model (current Groq
    model vs. Amazon Bedrock's Claude Haiku 4.5 / Sonnet 5 / Opus 4.8) so
    you can see what switching provider would actually cost, based on real
    volume rather than a guess. Cheapest model first in `projected_by_model`.
    """
    return get_model_cost_comparison(db)


@router.get("/benchmark/tasks", response_model=List[TaskBenchmark])
def get_task_benchmark(
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin),
):
    """
    Per-task aggregates ordered by total token consumption (heaviest first).

    Key field: estimation_accuracy
      1.0  → perfect pre-execution estimate
      >1.0 → over-estimated (safe, just slightly pessimistic)
      <1.0 → under-estimated (prompt contains more content than expected)
      null → no pre-execution estimates recorded yet for this task
    """
    return get_benchmark_by_task(db)


@router.get("/benchmark/daily", response_model=List[DailyBenchmark])
def get_daily_benchmark(
    days: int = Query(default=30, ge=1, le=365, description="Number of past days to include"),
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin),
):
    """Daily token and cost timeline. Use `days` to control the window."""
    return get_benchmark_over_time(db, days=days)


@router.get("/high-token")
def list_high_token_calls(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin),
):
    """Most expensive individual LLM calls (above the high-token threshold)."""
    return get_high_token_calls(db, limit=limit)


@router.get("/calls")
def list_recent_calls(
    task_name: Optional[str] = Query(default=None, description="Filter by task name"),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin),
):
    """
    Recent LLM call log.
    Each row shows actual vs estimated prompt tokens when available,
    so you can spot which calls deviate most from the pre-execution estimate.
    """
    return get_recent_calls(db, limit=limit, task_name=task_name)


@router.post("/estimate", response_model=EstimateResponse)
def estimate_llm_usage(
    body: EstimateRequest,
    current_user: User = Depends(require_admin_or_operator),
):
    """
    Pre-execution token and cost estimate for an automation run.

    Call this BEFORE launching a plan so the user sees an estimated cost
    on the "Review & Run" step. No LLM call is made — pure token counting.

    - instruction:         Natural-language automation instruction
    - context_endpoints:   Top-k endpoints the planner will receive (RAG results)
    - plan_steps:          Known step count (0 = skip validation estimate)
    """
    return estimate_run_cost(
        instruction=body.instruction,
        context_endpoints=body.context_endpoints,
        plan_steps=body.plan_steps,
    )


@router.post("/estimate/har")
async def estimate_har_llm_usage(
    file: UploadFile = File(..., description="HAR file to estimate token usage for"),
    current_user: User = Depends(require_admin_or_operator),
):
    """
    Estimate min/max LLM token usage for the ARIA ingestion pipeline on a HAR file.

    No LLM call is made — static analysis only:
      - Parses the HAR entries
      - Applies the same heuristic scoring used by the real ingestion pipeline
      - Computes per-stage token estimates for normalizer, schema_inference,
        payload_classifier, and endpoint_understanding

    Returns two scenarios:
      - **min**: strict API candidate filter + deduplication applied
      - **max**: loose filter + no deduplication (worst case)

    Use this on the Upload page before starting a full analysis run.
    """
    raw = await file.read()
    try:
        har_data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid JSON in HAR file: {exc}") from exc

    if "log" not in har_data:
        raise HTTPException(status_code=422, detail='HAR file must contain a top-level "log" key')

    return estimate_har_tokens(har_data)
