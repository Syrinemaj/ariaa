"""
Tâche Celery — génération du rapport d'exécution bulk.

Enfilée automatiquement par execute_batch_task quand tous les batches
d'un job sont terminés (détection par Redis : batches_done == batches).
Queue : "reporting" (concurrency=2).
"""
from __future__ import annotations

import asyncio
import logging

from app.workers.celery_app import celery_app
from app.workers.tasks.deduplication import deduplicated_task, report_key

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="aria.tasks.reporting.generate_bulk_report",
    queue="reporting",
    acks_late=True,
    max_retries=2,
    default_retry_delay=30,
)
@deduplicated_task(key_fn=report_key, timeout_seconds=300)
def generate_bulk_report(self, run_id: str, job_id: str, org_id: str) -> dict:
    """
    Génère et persiste le rapport de synthèse d'une exécution bulk.
    Peut être appelé manuellement ou automatiquement après la fin des batches.
    """
    try:
        result = asyncio.run(_run_report_async(run_id=run_id, job_id=job_id, org_id=org_id))
        logger.info("Report generated for run=%s job=%s", run_id, job_id)
        return result
    except Exception as exc:
        logger.error("Report generation failed for run=%s: %s", run_id, exc)
        raise self.retry(exc=exc) if self.request.retries < self.max_retries else exc


async def _run_report_async(run_id: str, job_id: str, org_id: str) -> dict:
    from app.db.session import AsyncSessionLocal
    from app.models.automation import AutomationRun
    from app.models.bulk_batch import BulkBatch
    from sqlalchemy import func, select

    async with AsyncSessionLocal() as db:
        run_result = await db.execute(
            select(AutomationRun).where(AutomationRun.id == run_id)
        )
        automation_run = run_result.scalar_one_or_none()

        if not automation_run:
            return {"error": f"AutomationRun {run_id!r} not found"}

        batch_result = await db.execute(
            select(
                func.sum(BulkBatch.success_count).label("total_success"),
                func.sum(BulkBatch.failed_count).label("total_failed"),
                func.count().label("total_batches"),
            ).where(BulkBatch.automation_run_id == run_id)
        )
        stats = batch_result.one()

        # Update the AutomationRun with final stats
        automation_run.success_count = stats.total_success or 0
        automation_run.failed_count = stats.total_failed or 0
        automation_run.status = "success" if (stats.total_failed or 0) == 0 else "partial_success"
        automation_run.result_json = {
            "report_generated_at": __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ).isoformat(),
            "total_success": stats.total_success or 0,
            "total_failed": stats.total_failed or 0,
            "total_batches": stats.total_batches or 0,
            "job_id": job_id,
        }

        await db.commit()

    return {
        "run_id": run_id,
        "job_id": job_id,
        "success_count": stats.total_success or 0,
        "failed_count": stats.total_failed or 0,
        "status": automation_run.status,
    }
