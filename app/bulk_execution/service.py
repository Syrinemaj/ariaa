"""
Bulk execution service — enqueue Celery tasks, return job_id immediately.

Previously this function ran the entire pipeline synchronously, blocking for
hours on large datasets. Now it:
1. Creates / reuses the AutomationRun DB record
2. Splits valid rows into batches (BULK_BATCH_SIZE rows each)
3. Initialises a Redis job-tracking hash
4. Enqueues one Celery task per batch
5. Returns immediately with job tracking metadata

Results are polled via GET /jobs/{job_id}/progress.
"""
from __future__ import annotations

import json
from typing import Optional
from uuid import uuid4

from sqlalchemy.orm import Session

from app.bulk_execution.batch_builder import split_into_batches
from app.bulk_execution.resume import get_completed_batch_numbers, should_skip_batch
from app.core.config import settings
from app.db.redis_client import get_redis
from app.models.automation import AutomationRun
from app.models.data_file import DataRow
from app.planner.models import AutomationPlan

_JOB_TTL = 86_400   # 24 h

# Row statuses that a new execution of the file picks up. "failed" is
# included so a file can be relaunched after a partial failure (e.g. the
# target was down and the circuit breaker short-circuited the remaining
# rows): without it every failed row was silently ineligible and the call
# answered "every row ... already executed successfully", which was false.
# Rows that succeeded ("success", "success_duplicate") are never picked up
# again; the idempotency store additionally guards against double-sends and
# explicitly allows a retry of a key whose last attempt failed.
ELIGIBLE_ROW_STATUSES = ("valid", "dry_run_success", "failed")


async def execute_valid_rows_in_batches(
    db: Session,
    plan: AutomationPlan,
    data_file_id: str,
    connection_id: str,
    dry_run: bool = True,
    batch_size: int | None = None,
    allow_partial_execution: bool = True,
    org_id: Optional[str] = None,
    created_by_user_id: Optional[str] = None,
    team_id: Optional[str] = None,
    resume: bool = False,
    existing_automation_run_id: Optional[str] = None,
    har_file_name: Optional[str] = None,
) -> dict:
    """
    Validate rows, create AutomationRun, enqueue batch Celery tasks.
    Returns job tracking info immediately (HTTP 202 pattern).
    """
    effective_batch_size = batch_size or settings.BULK_BATCH_SIZE

    # ── 1. Query rows ─────────────────────────────────────────────────────────
    # "dry_run_success" (not just "valid") is eligible here too: a dry run
    # never mutates real data, it only proves a row would succeed — but
    # batch_executor.py overwrites a row's status to "dry_run_success" once
    # its dry run completes, so a real execution that only looked for
    # "valid" found zero rows for any file that had ever been dry-run first
    # (every file, in practice, since dry-run-before-real is the normal
    # flow) — the job was created with total=0/batches=0 and sat at
    # "queued" forever, looking stuck rather than erroring.
    valid_rows = (
        db.query(DataRow)
        .filter(DataRow.data_file_id == data_file_id, DataRow.status.in_(ELIGIBLE_ROW_STATUSES))
        .order_by(DataRow.row_index.asc())
        .all()
    )

    invalid_rows_count = (
        db.query(DataRow)
        .filter(DataRow.data_file_id == data_file_id, DataRow.status == "invalid")
        .count()
    )

    if invalid_rows_count > 0 and not allow_partial_execution:
        raise ValueError(
            f"{invalid_rows_count} invalid rows found. "
            "Set allow_partial_execution=True to proceed anyway."
        )

    # No eligible rows — e.g. every row in this file was already executed for
    # real (status="success") by a previous call, or every row is "invalid"
    # and allow_partial_execution let that pass instead of raising above.
    # Without this guard the code below still created a job (total=0,
    # batches=0), which then sat at status="queued" forever: zero batches
    # enqueued means the "mark the job done" signal (fired when the last
    # batch reports in) never happens. Fail fast instead, same as the
    # all-invalid-and-not-partial case just above.
    if not valid_rows:
        raise ValueError(
            "No rows available to execute — every row in this file has "
            "already been executed successfully, or none passed validation "
            "(failed rows are always eligible for a new execution)."
        )

    # ── 2. Create / reuse AutomationRun ──────────────────────────────────────
    # existing_automation_run_id is also set (without resume=True) when a
    # pending-approval run just got admin-approved — see app/api/bulk.py —
    # reusing it instead of creating a duplicate row, so the AutomationRun
    # that was shown as "pending_approval" in GET /approvals correctly flips
    # to "running" rather than being left stranded forever.
    if existing_automation_run_id:
        automation_run = db.query(AutomationRun).filter(
            AutomationRun.id == existing_automation_run_id
        ).first()
        if not automation_run:
            raise ValueError(
                f"AutomationRun {existing_automation_run_id!r} not found."
            )
        automation_run.status = "running"
        db.commit()
    else:
        automation_run = AutomationRun(
            analysis_run_id=plan.run_id,
            instruction=plan.instruction,
            workflow_name=plan.workflow_name,
            dry_run=dry_run,
            source="bulk",
            status="running",
            total_steps=len(valid_rows) * len(plan.steps),
            plan_json=plan.model_dump(),
            org_id=org_id or "",
            created_by_user_id=created_by_user_id,
            team_id=team_id,
            connection_id=connection_id,
        )
        db.add(automation_run)
        db.commit()
        db.refresh(automation_run)

    # ── 3. Split into batches ─────────────────────────────────────────────────
    completed_batches = (
        get_completed_batch_numbers(db, automation_run.id) if resume else set()
    )
    batches = split_into_batches(valid_rows, batch_size=effective_batch_size)
    job_id = str(uuid4())

    # ── 4. Initialise Redis job tracking ──────────────────────────────────────
    redis = get_redis()
    redis.hset(
        f"job:{job_id}",
        mapping={
            "status": "queued",
            "total": len(valid_rows),
            "completed": 0,
            "failed": 0,
            "batches": len(batches),
            "batches_done": 0,
            "automation_run_id": automation_run.id,
            "data_file_id": data_file_id,
            "dry_run": "1" if dry_run else "0",
            "org_id": org_id or "",  # stored for cross-org ownership checks in GET /jobs/
            "created_by_user_id": created_by_user_id or "",  # who to notify on completion
            "har_file_name": har_file_name or "",
            "connection_id": connection_id,
        },
    )
    redis.expire(f"job:{job_id}", _JOB_TTL)

    # ── 5. Enqueue Celery tasks ───────────────────────────────────────────────
    from app.workers.tasks.execution import execute_batch_task

    enqueued = 0
    for batch_num, batch_rows in enumerate(batches, start=1):
        if should_skip_batch(batch_num, completed_batches, resume):
            redis.setex(f"job:{job_id}:batch:{batch_num}", _JOB_TTL, "completed")
            continue

        redis.setex(f"job:{job_id}:batch:{batch_num}", _JOB_TTL, "queued")

        # Row IDs are fixed here, at split time — the worker must fetch exactly
        # these rows, NOT re-query "WHERE status='valid' OFFSET/LIMIT", because
        # other batches flip rows to "success" concurrently and would shrink/shift
        # that filtered set out from under a re-query (see batch_builder.py).
        execute_batch_task.apply_async(
            kwargs={
                "job_id": job_id,
                "automation_run_id": automation_run.id,
                "data_file_id": data_file_id,
                "batch_number": batch_num,
                "row_ids": [row.id for row in batch_rows],
                "plan_json": plan.model_dump(),
                "connection_id": connection_id,
                "dry_run": dry_run,
                "org_id": org_id or "",
            },
        )
        enqueued += 1

    return {
        "job_id": job_id,
        "automation_run_id": automation_run.id,
        "status": "queued",
        "total_rows": len(valid_rows),
        "invalid_rows": invalid_rows_count,
        "batches": len(batches),
        "batches_enqueued": enqueued,
        "batches_skipped": len(batches) - enqueued,
    }
