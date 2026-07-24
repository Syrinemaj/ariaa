"""
Tâche Celery — exécution d'un batch de lignes (bulk automation).

Déduplication : lock Redis sur (job_id, batch_number).
Queue : "execution" (concurrency=10 car IO-bound : httpx + PostgreSQL).
Advisory lock PostgreSQL pour éviter la double-exécution même en cas de retry.
Commits intermédiaires toutes les BATCH_COMMIT_SIZE lignes.
"""
from __future__ import annotations

import asyncio
import logging
import traceback

from app.workers.celery_app import celery_app
from app.db.redis_client import get_redis
from app.workers.tasks.deduplication import batch_key, deduplicated_task

logger = logging.getLogger(__name__)

_JOB_TTL = 86_400


def _update_batch_status(job_id: str, batch_number: int, status: str) -> None:
    get_redis().setex(f"job:{job_id}:batch:{batch_number}", _JOB_TTL, status)


def _update_job_progress(
    job_id: str,
    batch_failed: bool = False,
) -> None:
    # NOTE: "completed"/"failed" row counts are incremented directly by
    # batch_executor.py (atomic hincrby of the delta, as rows complete) — not
    # here. This function only tracks batch-level completion and overall
    # job status, so it must not re-add per-row deltas on top of those.
    redis = get_redis()
    if batch_failed:
        redis.hincrby(f"job:{job_id}", "batches_failed", 1)
    redis.hincrby(f"job:{job_id}", "batches_done", 1)

    data = redis.hgetall(f"job:{job_id}")
    batches = int(data.get("batches", 0))
    batches_done = int(data.get("batches_done", 0))
    completed = int(data.get("completed", 0))
    failed_total = int(data.get("failed", 0))
    batches_failed_total = int(data.get("batches_failed", 0))

    # Transition queued → running on first batch update
    if data.get("status") == "queued":
        redis.hset(f"job:{job_id}", "status", "running")

    # Completion: all batches have reported in (success or final failure)
    if batches and batches_done >= batches:
        if completed == 0 and batches_failed_total > 0:
            final_status = "failed"
        elif failed_total > 0 or batches_failed_total > 0:
            final_status = "partial"
        else:
            final_status = "done"
        redis.hset(f"job:{job_id}", "status", final_status)

        automation_run_id = data.get("automation_run_id", "")
        org_id = data.get("org_id", "")
        if automation_run_id:
            from app.workers.tasks.reporting import generate_bulk_report
            generate_bulk_report.apply_async(
                kwargs={
                    "run_id": automation_run_id,
                    "job_id": job_id,
                    "org_id": org_id,
                },
                queue="reporting",
            )

    redis.expire(f"job:{job_id}", _JOB_TTL)


@celery_app.task(
    bind=True,
    name="aria.tasks.execution.execute_batch",
    queue="execution",
    acks_late=True,
    reject_on_worker_lost=True,
    max_retries=3,
    default_retry_delay=15,
)
@deduplicated_task(key_fn=batch_key, timeout_seconds=1800)
def execute_batch_task(
    self,
    job_id: str,
    automation_run_id: str,
    data_file_id: str,
    batch_number: int,
    row_ids: list,
    plan_json: dict,
    base_url: str,
    auth_headers: dict,
    dry_run: bool,
    org_id: str = "",
) -> dict:
    _update_batch_status(job_id, batch_number, "running")

    # Celery uses prefork — the async_engine connection pool is inherited from
    # the parent process and attached to the parent's event loop.  asyncio.run()
    # creates a NEW event loop in the forked child, causing
    # "Future attached to a different loop" errors on first DB call.
    # Disposing the pool forces fresh connections bound to the new loop.
    try:
        from app.db.session import async_engine as _async_engine
        _async_engine.sync_engine.dispose()
    except Exception:
        pass

    try:
        result = asyncio.run(
            _run_batch_async(
                job_id=job_id,
                automation_run_id=automation_run_id,
                data_file_id=data_file_id,
                batch_number=batch_number,
                row_ids=row_ids,
                plan_json=plan_json,
                base_url=base_url,
                auth_headers=auth_headers,
                dry_run=dry_run,
                org_id=org_id,
            )
        )

        _update_batch_status(job_id, batch_number, "completed")
        _update_job_progress(job_id)
        logger.info(
            "Batch %d/%s completed: %d ok / %d failed",
            batch_number, job_id,
            result.get("success_count", 0),
            result.get("failed_count", 0),
        )
        return result

    except Exception as exc:
        _update_batch_status(job_id, batch_number, "failed")
        logger.error(
            "Batch %d/%s failed: %s\n%s",
            batch_number, job_id, exc, traceback.format_exc(limit=8),
        )
        if self.request.retries >= self.max_retries:
            # Final failure — update progress so the job can still reach completion
            _update_job_progress(job_id, batch_failed=True)
        raise self.retry(exc=exc) if self.request.retries < self.max_retries else exc


async def _run_batch_async(
    job_id: str,
    automation_run_id: str,
    data_file_id: str,
    batch_number: int,
    row_ids: list,
    plan_json: dict,
    base_url: str,
    auth_headers: dict,
    dry_run: bool,
    org_id: str = "",
) -> dict:
    import redis.asyncio as aioredis

    from app.bulk_execution.batch_executor import execute_batch
    from app.core.config import settings as _settings
    from app.db.session import AsyncSessionLocal
    from app.models.data_file import DataRow
    from app.planner.models import AutomationPlan
    from app.resilience.circuit_breaker import RedisCircuitBreakerRegistry
    from app.security.ssrf_guard import create_safe_client
    from sqlalchemy import select

    plan = AutomationPlan.model_validate(plan_json)

    async with AsyncSessionLocal() as db:
        # Fetch by the exact row IDs assigned to this batch at split time — NOT
        # by re-querying "WHERE status='valid' OFFSET/LIMIT". That filter mutates
        # as sibling batches flip rows to "success" concurrently, so a live
        # re-query silently drops or duplicates rows across batches at scale.
        # Retry safety for already-completed rows is handled by the idempotency
        # layer in batch_executor.py, not by a status filter here.
        result = await db.execute(
            select(DataRow)
            .where(
                DataRow.data_file_id == data_file_id,
                DataRow.id.in_(row_ids),
            )
            .order_by(DataRow.row_index.asc())
        )
        rows = list(result.scalars().all())

        if not rows:
            logger.warning("Batch %d/%s has no valid rows", batch_number, job_id)
            return {
                "batch_number": batch_number,
                "rows_count": 0,
                "success_count": 0,
                "failed_count": 0,
                "errors": [],
            }

        async_redis = aioredis.from_url(
            _settings.REDIS_APP_URL, decode_responses=True
        )
        circuit_registry = RedisCircuitBreakerRegistry(async_redis)

        async with create_safe_client(base_url) as client:
            batch_result = await execute_batch(
                db=db,
                automation_run_id=automation_run_id,
                plan=plan,
                batch_number=batch_number,
                rows=rows,
                base_url=base_url,
                auth_headers=auth_headers,
                dry_run=dry_run,
                client=client,
                job_id=job_id,
                circuit_registry=circuit_registry,
                org_id=org_id,
            )

    return batch_result
