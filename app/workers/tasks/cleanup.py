"""
Tâche Celery — nettoyage des fichiers HAR et runs orphelins.

Planifié via Celery Beat (voir celery_app.py beat_schedule).
Queue : "maintenance" (concurrency=1, basse priorité).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.workers.celery_app import celery_app
from app.core.config import settings

logger = logging.getLogger(__name__)


@celery_app.task(
    name="aria.tasks.cleanup.cleanup_expired_files",
    queue="maintenance",
    acks_late=True,
    max_retries=1,
)
def cleanup_expired_files() -> dict:
    """
    Supprime les fichiers HAR dont le TTL est dépassé.
    Nettoie également les runs AnalysisRun orphelins (sans endpoints).
    """
    import asyncio
    result = asyncio.run(_run_cleanup_async())
    logger.info("Cleanup done: %s", result)
    return result


async def _run_cleanup_async() -> dict:
    from app.db.session import AsyncSessionLocal
    from app.models.analysis_run import AnalysisRun
    from sqlalchemy import select, delete

    upload_dir = Path(settings.UPLOAD_DIR)
    now = datetime.now(timezone.utc)
    ttl_ok = timedelta(days=settings.UPLOAD_FILE_TTL_DAYS)
    ttl_fail = timedelta(hours=settings.UPLOAD_FAILED_FILE_TTL_HOURS)
    dry_run = settings.CLEANUP_DRY_RUN

    deleted_files = 0
    skipped_files = 0

    # ── 1. Nettoyage des fichiers sur disque ──────────────────────────────────
    if upload_dir.exists():
        for file_path in upload_dir.glob("*.har"):
            try:
                mtime = datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc)
                age = now - mtime
                if age > ttl_ok:
                    if not dry_run:
                        file_path.unlink()
                    deleted_files += 1
                    logger.debug("Deleted (TTL): %s (age=%s)", file_path, age)
                else:
                    skipped_files += 1
            except OSError as e:
                logger.warning("Could not process %s: %s", file_path, e)

    # ── 2. Nettoyage des runs orphelins ───────────────────────────────────────
    deleted_runs = 0
    async with AsyncSessionLocal() as db:
        from sqlalchemy import text
        cutoff = now - ttl_ok
        result = await db.execute(
            select(AnalysisRun.id)
            .where(
                AnalysisRun.created_at < cutoff,
                ~AnalysisRun.id.in_(
                    select(text("run_id")).select_from(
                        text("endpoints")
                    )
                ),
            )
            .limit(500)
        )
        orphan_ids = [r[0] for r in result.all()]

        if orphan_ids and not dry_run:
            await db.execute(
                delete(AnalysisRun).where(AnalysisRun.id.in_(orphan_ids))
            )
            await db.commit()
            deleted_runs = len(orphan_ids)

    return {
        "dry_run": dry_run,
        "deleted_files": deleted_files,
        "skipped_files": skipped_files,
        "deleted_orphan_runs": deleted_runs,
    }
