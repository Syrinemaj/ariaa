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


def _update_job_progress(job_id: str, success_delta: int, failed_delta: int) -> None:
    redis = get_redis()
    if success_delta:
        redis.hincrby(f"job:{job_id}", "completed", success_delta)
    if failed_delta:
        redis.hincrby(f"job:{job_id}", "failed", failed_delta)
    redis.hincrby(f"job:{job_id}", "batches_done", 1)

    data = redis.hgetall(f"job:{job_id}")
    total = int(data.get("total", 0))
    completed = int(data.get("completed", 0))
    failed_total = int(data.get("failed", 0))

    if total and completed + failed_total >= total:
        status = "done" if failed_total == 0 else "partial"
        redis.hset(f"job:{job_id}", "status", status)

        # All batches done → trigger report generation
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
    batch_size: int,
    plan_json: dict,
    base_url: str,
    auth_headers: dict,
    dry_run: bool,
    org_id: str = "",
) -> dict:
    _update_batch_status(job_id, batch_number, "running")

    try:
        result = asyncio.run(
            _run_batch_async(
                job_id=job_id,
                automation_run_id=automation_run_id,
                data_file_id=data_file_id,
                batch_number=batch_number,
                batch_size=batch_size,
                plan_json=plan_json,
                base_url=base_url,
                auth_headers=auth_headers,
                dry_run=dry_run,
                org_id=org_id,
            )
        )

        _update_batch_status(job_id, batch_number, "completed")
        _update_job_progress(
            job_id,
            success_delta=result.get("success_count", 0),
            failed_delta=result.get("failed_count", 0),
        )
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
        raise self.retry(exc=exc) if self.request.retries < self.max_retries else exc


async def _run_batch_async(
    job_id: str,
    automation_run_id: str,
    data_file_id: str,
    batch_number: int,
    batch_size: int,
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
        offset = (batch_number - 1) * batch_size
        result = await db.execute(
            select(DataRow)
            .where(
                DataRow.data_file_id == data_file_id,
                DataRow.status == "valid",
            )
            .order_by(DataRow.row_index.asc())
            .offset(offset)
            .limit(batch_size)
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
