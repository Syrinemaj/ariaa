"""
Tâche Celery — pipeline complet d'ingestion HAR.

Chaîne automatique : ingestion → embedding (task Celery séparé).
Déduplication : lock Redis sur sha256(file_path + org_id).
Queue : "ingestion" (workers dédiés, concurrency=2 car LLM-bound).
"""
from __future__ import annotations

import asyncio
import json
import logging
import traceback
from datetime import datetime, timezone
from pathlib import Path

from app.workers.celery_app import celery_app
from app.db.redis_client import get_redis
from app.workers.tasks.deduplication import deduplicated_task, har_pipeline_key

logger = logging.getLogger(__name__)

_JOB_TTL = 86_400


def _set_job_status(job_id: str, status: str, **extra) -> None:
    redis = get_redis()
    redis.setex(
        f"job:{job_id}",
        _JOB_TTL,
        json.dumps({
            "job_id": job_id,
            "status": status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            **extra,
        }),
    )


@celery_app.task(
    bind=True,
    name="aria.tasks.ingestion.process_har_pipeline",
    queue="ingestion",
    acks_late=True,
    reject_on_worker_lost=True,
    max_retries=2,
    default_retry_delay=30,
)
@deduplicated_task(key_fn=har_pipeline_key, timeout_seconds=600)
def process_har_pipeline(
    self,
    job_id: str,
    file_path: str,
    file_name: str,
    org_id: str,
    user_id: str,
    options: dict,
) -> dict:
    """
    Pipeline complet : parse HAR → normalise → schémas → workflows → BDD.
    Enfile automatiquement index_run_embeddings à la fin.
    """
    _set_job_status(job_id, "processing")

    try:
        result = asyncio.run(_run_ingestion_async(
            job_id=job_id,
            file_path=file_path,
            file_name=file_name,
            org_id=org_id,
            user_id=user_id,
            options=options,
        ))

        _set_job_status(job_id, "completed", result=result)

        # Automatically chain embedding indexing
        from app.workers.tasks.embedding import index_run_embeddings
        index_run_embeddings.apply_async(
            kwargs={"run_id": result["run_id"], "org_id": org_id},
            queue="embedding",
        )

        return result

    except Exception as exc:
        _set_job_status(
            job_id, "failed",
            error=str(exc),
            traceback=traceback.format_exc(limit=10),
        )
        raise self.retry(exc=exc) if self.request.retries < self.max_retries else exc


async def _run_ingestion_async(
    job_id: str,
    file_path: str,
    file_name: str,
    org_id: str,
    user_id: str,
    options: dict,
) -> dict:
    from app.db.session import AsyncSessionLocal
    from app.ingestion.service import process_har_file
    from app.normalization.service import normalize_entries
    from app.registry.repository import (
        create_analysis_run,
        save_endpoint_schema_result,
        save_workflow,
    )
    from app.schema_inference.service import infer_schemas_for_endpoints
    from app.workflows.clustering import discover_workflows

    use_phase2_ai: bool = options.get("use_phase2_ai", True)
    use_norm_ai: bool = options.get("use_normalization_ai", True)
    deduplicate: bool = options.get("deduplicate", True)

    cleaned_entries = process_har_file(
        file_path=Path(file_path),
        use_ai=use_phase2_ai,
        only_candidates=True,
    )

    normalized_endpoints = normalize_entries(
        entries=cleaned_entries,
        use_ai=use_norm_ai,
        deduplicate=deduplicate,
    )

    schema_results = infer_schemas_for_endpoints(normalized_endpoints)
    workflows = discover_workflows(normalized_endpoints)

    async with AsyncSessionLocal() as db:
        run = await create_analysis_run(
            db=db,
            file_name=file_name,
            total_cleaned_api_calls=len(cleaned_entries),
            total_normalized_endpoints=len(normalized_endpoints),
            total_schema_results=len(schema_results),
            org_id=org_id,
            created_by_user_id=user_id,
        )

        saved_endpoints = []
        for result in schema_results:
            ep = await save_endpoint_schema_result(
                db=db, run_id=run.id, result=result, org_id=org_id
            )
            saved_endpoints.append(ep)

        saved_workflows = [
            await save_workflow(db=db, run_id=run.id, workflow=wf)
            for wf in workflows
        ]

        await db.commit()

    return {
        "run_id": run.id,
        "cleaned_api_calls": len(cleaned_entries),
        "normalized_endpoints": len(normalized_endpoints),
        "schema_results": len(schema_results),
        "saved_endpoints": len(saved_endpoints),
        "saved_workflows": len(saved_workflows),
        "workflow_names": [wf.name for wf in saved_workflows],
    }
