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
_AI_ENRICHMENT_CONCURRENCY = 8


def _set_job_status(job_id: str, status: str, org_id: str | None = None, **extra) -> None:
    redis = get_redis()
    redis.setex(
        f"job:{job_id}",
        _JOB_TTL,
        json.dumps({
            "job_id": job_id,
            "status": status,
            "org_id": org_id,
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
    team_id: str | None = None,
) -> dict:
    """
    Pipeline complet : parse HAR → normalise → schémas → workflows → BDD.
    Enfile automatiquement index_run_embeddings à la fin.
    """
    _set_job_status(job_id, "processing", org_id=org_id)

    try:
        result = asyncio.run(_run_ingestion_async(
            job_id=job_id,
            file_path=file_path,
            file_name=file_name,
            org_id=org_id,
            user_id=user_id,
            options=options,
            team_id=team_id,
        ))

        # Enqueue embedding BEFORE marking completed so a Redis flush between
        # the two calls cannot leave the run as "completed" without embeddings.
        from app.workers.tasks.embedding import index_run_embeddings
        index_run_embeddings.apply_async(
            kwargs={"run_id": result["run_id"], "org_id": org_id},
            queue="embedding",
        )

        _set_job_status(job_id, "completed", org_id=org_id, result=result)
        return result

    except Exception as exc:
        _set_job_status(
            job_id, "failed", org_id=org_id,
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
    team_id: str | None = None,
) -> dict:
    # Create a task-local async engine so each asyncio.run() call has its own
    # connection pool bound to the current event loop. The global async_engine
    # is bound to the FastAPI loop and must not be reused across asyncio.run()
    # calls in Celery workers (causes "Future attached to a different loop").
    import re
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.core.config import settings

    _db_url = re.sub(r"^postgresql(\+\w+)?://", "postgresql+asyncpg://", settings.DATABASE_URL)
    _local_engine = create_async_engine(_db_url, pool_size=2, max_overflow=4, pool_pre_ping=True)
    AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
        _local_engine, class_=AsyncSession, expire_on_commit=False, autocommit=False, autoflush=False,
    )

    from app.ai.base_client import create_ai_client
    from app.ingestion.service import process_har_file
    from app.normalization.service import normalize_entries, normalize_entries_with_raw
    from app.registry.repository import (
        create_analysis_run,
        get_run_by_id,
        save_endpoint_schema_result,
        save_workflow,
    )
    from app.schema_inference.service import infer_schemas_for_endpoints
    from app.workflows.clustering import discover_workflows

    use_phase2_ai: bool = options.get("use_phase2_ai", True)
    use_norm_ai: bool = options.get("use_normalization_ai", True)
    deduplicate: bool = options.get("deduplicate", True)

    # ── Step 1 : create the run immediately so failures are auditable in DB ──
    async with AsyncSessionLocal() as db:
        run = await create_analysis_run(
            db=db,
            file_name=file_name,
            total_cleaned_api_calls=0,
            total_normalized_endpoints=0,
            total_schema_results=0,
            org_id=org_id,
            created_by_user_id=user_id,
            status="processing",
            team_id=team_id,
            job_id=job_id,
        )
        run_id = run.id
        await db.commit()

    try:
        # ── Step 2 : all sync processing (no DB) ─────────────────────────────
        cleaned_entries = process_har_file(
            file_path=Path(file_path),
            use_ai=use_phase2_ai,
            only_candidates=True,
        )

        if deduplicate:
            # raw_calls (pre-dedup, real per-call bodies) feeds the workflow
            # dependency detector's value-correlation pass — see
            # app/workflows/dependency_detector.py — so an "id" one call's
            # response actually produced can be matched against the same
            # value consumed by a later call's path/body, instead of only
            # guessing from step order or field names.
            normalized_endpoints, raw_calls = normalize_entries_with_raw(
                entries=cleaned_entries, use_ai=use_norm_ai,
            )
        else:
            normalized_endpoints = normalize_entries(
                entries=cleaned_entries, use_ai=use_norm_ai, deduplicate=False,
            )
            raw_calls = normalized_endpoints

        schema_results = infer_schemas_for_endpoints(normalized_endpoints)
        # ai_client/redis enable step reordering (sequence_builder) and rich
        # description/tags/risk (workflow_descriptor) — previously always
        # skipped here since discover_workflows() never received a real
        # ai_client, leaving that code unreachable in production. Workflow
        # naming itself stays keyword-based at this stage regardless (see
        # clustering.py docstring) — the LLM-refined name/domain/confidence
        # is set once, authoritatively, in Step 5 below.
        workflows = discover_workflows(
            normalized_endpoints, ai_client=create_ai_client(), redis=get_redis(), raw_calls=raw_calls,
        )

        # ── Step 3 : persist results ────────────────────────────────────────────
        # status stays "processing" here — Steps 4/5 below (AI enrichment) still
        # have to run. Flipping to "completed" this early let pollers see a
        # run as done while its business_domain/tags/workflow names were still
        # being written for another 1-2 minutes.
        async with AsyncSessionLocal() as db:
            run = await get_run_by_id(db, run_id, org_id)
            run.total_cleaned_api_calls = len(cleaned_entries)
            run.total_normalized_endpoints = len(normalized_endpoints)
            run.total_schema_results = len(schema_results)

            saved_endpoints = []
            for result in schema_results:
                ep = await save_endpoint_schema_result(
                    db=db, run_id=run_id, result=result, org_id=org_id
                )
                saved_endpoints.append(ep)

            saved_workflows = [
                await save_workflow(
                    db=db, run_id=run_id, workflow=wf, org_id=org_id
                )
                for wf in workflows
            ]

            await db.commit()

    except Exception:
        # ── Step 4 : mark failed if processing crashed ────────────────────────
        async with AsyncSessionLocal() as db:
            run = await get_run_by_id(db, run_id, org_id)
            if run:
                run.status = "failed"
                await db.commit()
        await _local_engine.dispose()
        raise

    # ── Step 4 : AI enrichment (endpoint_understanding) ──────────────────────
    enriched_count = 0
    try:
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        from app.models.endpoint import Endpoint
        from app.ai.base_client import create_ai_client
        from app.ai.endpoint_understanding import enrich_endpoint_with_ai
        from app.rag.pipeline import enrich_endpoints_metadata

        async with AsyncSessionLocal() as db:
            ep_res = await db.execute(
                select(Endpoint)
                .options(selectinload(Endpoint.schema))
                .where(Endpoint.run_id == run_id)
            )
            fresh_endpoints = list(ep_res.scalars().all())

            ai_client = create_ai_client()

            # One AI call per endpoint (up to ~70+ on a large HAR) — run
            # concurrently instead of sequentially, this loop alone was the
            # single largest contributor to ingestion wall time.
            enrich_sem = asyncio.Semaphore(_AI_ENRICHMENT_CONCURRENCY)

            async def _enrich_one(ep):
                async with enrich_sem:
                    try:
                        return ep.id, await asyncio.to_thread(
                            enrich_endpoint_with_ai, ep, ai_client
                        )
                    except Exception as ep_exc:
                        logger.warning("endpoint_enrichment.failed endpoint=%s error=%s", ep.id, ep_exc)
                        return ep.id, None

            enrich_pairs = await asyncio.gather(*[_enrich_one(ep) for ep in fresh_endpoints])
            enrichment_results = {eid: result for eid, result in enrich_pairs if result is not None}

            if enrichment_results:
                enriched_count = await enrich_endpoints_metadata(
                    db=db, run_id=run_id, enrichment_results=enrichment_results
                )
    except Exception as enrich_exc:
        logger.warning("endpoint_enrichment.step_failed run=%s error=%s", run_id, enrich_exc)

    # Workflow naming used to be a separate Step 5 here (enrich_workflow_with_ai,
    # workflow_understanding.py) that overwrote discover_workflows()'s
    # provisional names after the run was already saved — two LLM calls, two
    # sources of truth, and the cause of a real bug (this task's returned
    # result reported stale pre-rename names, since it held references to the
    # Step 3 objects a later, separate DB session mutated). A workflow is now
    # fully named at creation time in Step 2 — see clustering.py's module
    # docstring ("Naming ownership") — so there is nothing left to do here.

    # ── Step 5 : mark completed — only now that endpoint enrichment (Step 4)
    # has actually finished, best-effort or not (its own try/except above
    # already swallows and logs enrichment failures without failing the run).
    async with AsyncSessionLocal() as db:
        run = await get_run_by_id(db, run_id, org_id)
        if run:
            run.status = "completed"
            await db.commit()

    await _local_engine.dispose()
    return {
        "run_id": run_id,
        "cleaned_api_calls": len(cleaned_entries),
        "normalized_endpoints": len(normalized_endpoints),
        "schema_results": len(schema_results),
        "saved_endpoints": len(saved_endpoints),
        "saved_workflows": len(saved_workflows),
        "workflow_names": [wf.name for wf in saved_workflows],
        "enriched_endpoints": enriched_count,
    }
