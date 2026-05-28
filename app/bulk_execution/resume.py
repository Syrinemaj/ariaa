"""
Resume — re-enqueue failed or incomplete batches.

Two data sources for batch status:
1. Redis  → `job:{job_id}:batch:{n}` (fast, ephemeral — 24h TTL)
2. DB     → BulkBatch.status (durable, always available)

Resume strategy:
  - Find all BulkBatch records for this automation_run_id
  - Re-enqueue batches where DB status != "completed"
  - Use Redis to mark re-enqueued batches as "queued" again
"""
from __future__ import annotations

from typing import Optional, Set

from sqlalchemy.orm import Session

from app.db.redis_client import get_redis
from app.models.bulk_batch import BulkBatch

_JOB_TTL = 86_400  # 24 h


# ─── DB-backed helpers (used by service.py during initial enqueueing) ─────────

def get_completed_batch_numbers(db: Session, automation_run_id: str) -> Set[int]:
    """Return batch numbers where DB status = 'completed'."""
    rows = (
        db.query(BulkBatch.batch_number)
        .filter(
            BulkBatch.automation_run_id == automation_run_id,
            BulkBatch.status == "completed",
        )
        .all()
    )
    return {r.batch_number for r in rows}


def should_skip_batch(
    batch_number: int,
    completed_batch_numbers: Set[int],
    resume: bool,
) -> bool:
    return resume and batch_number in completed_batch_numbers


# ─── Re-enqueue failed batches ────────────────────────────────────────────────

def resume_job(
    db: Session,
    job_id: str,
    automation_run_id: str,
    data_file_id: str,
    plan_json: dict,
    base_url: str,
    auth_headers: dict,
    dry_run: bool,
    batch_size: int,
    org_id: str = "",
) -> dict:
    """
    Re-enqueue all batches for an automation_run that did NOT complete.

    Identifies incomplete batches from the DB (durable source of truth).
    Redis may have expired, so DB is always consulted.
    """
    from app.workers.tasks.execution import execute_batch_task

    redis = get_redis()

    # All batches for this run
    all_batches = (
        db.query(BulkBatch)
        .filter(BulkBatch.automation_run_id == automation_run_id)
        .order_by(BulkBatch.batch_number.asc())
        .all()
    )

    incomplete = [b for b in all_batches if b.status != "completed"]

    if not incomplete:
        return {
            "job_id": job_id,
            "message": "All batches already completed. Nothing to resume.",
            "resumed_batches": 0,
        }

    # Re-initialise Redis tracking for the resumed job
    redis.hset(
        f"job:{job_id}",
        mapping={"status": "running"},
    )
    redis.expire(f"job:{job_id}", _JOB_TTL)

    enqueued = 0
    for batch in incomplete:
        redis.setex(f"job:{job_id}:batch:{batch.batch_number}", _JOB_TTL, "queued")
        execute_batch_task.apply_async(
            kwargs={
                "job_id": job_id,
                "automation_run_id": automation_run_id,
                "data_file_id": data_file_id,
                "batch_number": batch.batch_number,
                "batch_size": batch_size,
                "plan_json": plan_json,
                "base_url": base_url,
                "auth_headers": auth_headers,
                "dry_run": dry_run,
                "org_id": org_id,
            },
        )
        enqueued += 1

    return {
        "job_id": job_id,
        "automation_run_id": automation_run_id,
        "resumed_batches": enqueued,
        "status": "requeued",
    }
