"""
Job status endpoints — polling interface for async operations.

Three endpoints:
  GET  /jobs/{job_id}           → generic job status (HAR ingestion, etc.)
  GET  /jobs/{job_id}/progress  → detailed bulk-execution progress counters
  POST /jobs/{job_id}/cancel    → request cancellation of a running bulk job
"""
import json

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_admin_or_operator
from app.db.redis_client import get_redis
from app.db.session import get_db
from app.models.analysis_run import AnalysisRun
from app.models.user import User

router = APIRouter(prefix="/jobs", tags=["Jobs"])

_JOB_TTL = 86_400  # matches app/bulk_execution/service.py and app/workers/tasks/execution.py

_CANCELLABLE_STATUSES = {"queued", "running", "cancelling"}


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
    dry_run: bool = True


@router.get("/{job_id}", response_model=JobStatus)
async def get_job_status(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin_or_operator),
):
    """Generic job status (e.g. HAR ingestion pipeline)."""
    redis = get_redis()
    raw = redis.get(f"job:{job_id}")

    if raw is not None:
        data = json.loads(raw)
        job_org_id = data.get("org_id")
        if job_org_id and job_org_id != current_user.org_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found or expired (TTL 24h)",
            )
        return JobStatus(**data)

    # Redis key absent/expired (TTL 24h) — repli sur la ligne AnalysisRun
    # persistée, qui n'expire jamais, pour que le polling ne casse pas
    # définitivement juste parce que plus de 24h se sont écoulées.
    result = await db.execute(
        select(AnalysisRun).where(
            AnalysisRun.job_id == job_id, AnalysisRun.org_id == current_user.org_id
        )
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found or expired (TTL 24h)",
        )

    return JobStatus(
        job_id=job_id,
        status=run.status,
        updated_at=run.updated_at.isoformat() if run.updated_at else None,
        result={"run_id": run.id} if run.status == "completed" else None,
        error=None,
    )


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

    # BUG-009: verify job belongs to the caller's org (written by execute_valid_rows_in_batches)
    job_org_id = data.get("org_id")
    if job_org_id and job_org_id != current_user.org_id:
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
        dry_run=data.get("dry_run", "1") == "1",
    )


@router.post("/{job_id}/cancel")
async def cancel_bulk_job(
    job_id: str,
    current_user: User = Depends(require_admin_or_operator),
):
    """
    Requests cancellation of a running bulk job. Cooperative, not a hard
    kill: an HTTP call already in flight to the target API always finishes
    (can't safely abort mid-request — no way to know if the target already
    applied it), but no NEW row or batch starts once this flag is set. Rows
    not yet reached stay at whatever status they already had ("valid" /
    "dry_run_success"), untouched and resumable later via POST /bulk/resume
    — cancelling is not the same as failing them.

    Sets status="cancelling" immediately for instant UI feedback; the
    in-flight batch(es) flip it to the terminal "cancelled" once they
    actually stop (see app/bulk_execution/batch_executor.py and
    app/workers/tasks/execution.py::_update_job_progress).
    """
    redis = get_redis()
    data = redis.hgetall(f"job:{job_id}")
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found or expired (TTL 24h)")

    job_org_id = data.get("org_id")
    if job_org_id and job_org_id != current_user.org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found or expired (TTL 24h)")

    current_status = data.get("status", "")
    if current_status not in _CANCELLABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job is already {current_status!r} — nothing to cancel.",
        )

    redis.hset(f"job:{job_id}", mapping={"cancel_requested": "1", "status": "cancelling"})
    redis.expire(f"job:{job_id}", _JOB_TTL)
    return {"job_id": job_id, "status": "cancelling"}
