"""
Job status endpoints — polling interface for async operations.

Two endpoints:
  GET /jobs/{job_id}           → generic job status (HAR ingestion, etc.)
  GET /jobs/{job_id}/progress  → detailed bulk-execution progress counters
"""
import json

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.auth.dependencies import require_admin_or_operator
from app.db.redis_client import get_redis
from app.models.user import User

router = APIRouter(prefix="/jobs", tags=["Jobs"])


class JobStatus(BaseModel):
    job_id: str
    status: str
    updated_at: str | None = None
    result: dict | None = None
    error: str | None = None


class BulkJobProgress(BaseModel):
    job_id: str
    status: str            # queued | running | done | partial | failed
    total: int
    completed: int
    failed: int
    batches: int
    batches_done: int
    automation_run_id: str | None = None
    progress_pct: float    # 0–100


@router.get("/{job_id}", response_model=JobStatus)
async def get_job_status(
    job_id: str,
    current_user: User = Depends(require_admin_or_operator),
):
    """Generic job status (e.g. HAR ingestion pipeline)."""
    redis = get_redis()
    raw = redis.get(f"job:{job_id}")

    if raw is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found or expired (TTL 24h)",
        )

    data = json.loads(raw)
    return JobStatus(**data)


@router.get("/{job_id}/progress", response_model=BulkJobProgress)
async def get_bulk_job_progress(
    job_id: str,
    current_user: User = Depends(require_admin_or_operator),
):
    """
    Detailed progress for a bulk execution job.

    Reads from a Redis hash updated in real time by Celery workers:
      job:{job_id} → {status, total, completed, failed, batches, batches_done}

    Returns immediately from Redis — no DB query needed.
    """
    redis = get_redis()
    data = redis.hgetall(f"job:{job_id}")

    if not data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found or expired (TTL 24h)",
        )

    total = int(data.get("total", 0))
    completed = int(data.get("completed", 0))
    failed = int(data.get("failed", 0))
    batches = int(data.get("batches", 0))
    batches_done = int(data.get("batches_done", 0))

    progress_pct = round((completed + failed) / total * 100, 1) if total > 0 else 0.0

    return BulkJobProgress(
        job_id=job_id,
        status=data.get("status", "unknown"),
        total=total,
        completed=completed,
        failed=failed,
        batches=batches,
        batches_done=batches_done,
        automation_run_id=data.get("automation_run_id"),
        progress_pct=progress_pct,
    )
