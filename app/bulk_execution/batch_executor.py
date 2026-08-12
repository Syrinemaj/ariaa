"""
Batch executor — async SQLAlchemy + commits intermédiaires.

Fix 6.3 : utilise AsyncSession au lieu de Session synchrone.
Fix 6.5 : commit toutes les BATCH_COMMIT_SIZE lignes pour éviter le timeout
          de session sur de grands datasets (session timeout ≈ 30 min).

Advisory lock PostgreSQL :
  pg_advisory_xact_lock garantit qu'un seul worker Celery exécute
  ce batch à la fois, même en cas de re-queue après crash.
  La clé est hash(job_id + batch_number) modulo 2^31.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List

import httpx
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import sanitize_payload
from app.automation.executor import execute_step
from app.automation.payload_mapper import map_payload_for_step
from app.bulk_execution.batch_state import update_state_from_response
from app.db.redis_client import get_redis
from app.idempotency.service import save_success_idempotency, should_skip_due_to_idempotency
from app.models.automation import AutomationStepLog
from app.models.bulk_batch import BulkBatch, BulkBatchRow
from app.models.data_file import DataRow
from app.planner.models import AutomationPlan

# Commit toutes les N lignes — évite les sessions > 30 min
BATCH_COMMIT_SIZE = 10


async def execute_batch(
    db: AsyncSession,
    automation_run_id: str,
    plan: AutomationPlan,
    batch_number: int,
    rows: List[DataRow],
    base_url: str,
    auth_headers: dict,
    dry_run: bool,
    client: httpx.AsyncClient,
    job_id: str = "",
    circuit_registry=None,
    org_id: str = "",
) -> dict:
    started_at = time.time()

    # ── Advisory lock : un seul worker par batch ──────────────────────────────
    # La clé doit tenir dans un int32 PostgreSQL.
    if job_id:
        lock_key = abs(hash(f"{job_id}:{batch_number}")) % (2**31)
        await db.execute(
            text("SELECT pg_advisory_xact_lock(:k)"),
            {"k": lock_key},
        )

    batch = BulkBatch(
        automation_run_id=automation_run_id,
        batch_number=batch_number,
        start_row=rows[0].row_index if rows else 0,
        end_row=rows[-1].row_index if rows else 0,
        status="running",
    )
    db.add(batch)
    await db.flush()

    success_count = 0
    failed_count = 0
    row_errors: List[dict] = []

    redis = get_redis()

    # Deltas reported to the shared job counter so far — hincrby() is atomic
    # and additive across concurrent batches, unlike hset() which would
    # overwrite the cumulative total with this batch's local count alone.
    reported_success = 0
    reported_failed = 0

    def _report_progress_delta() -> None:
        nonlocal reported_success, reported_failed
        if not job_id:
            return
        success_delta = success_count - reported_success
        failed_delta = failed_count - reported_failed
        if success_delta:
            redis.hincrby(f"job:{job_id}", "completed", success_delta)
        if failed_delta:
            redis.hincrby(f"job:{job_id}", "failed", failed_delta)
        reported_success = success_count
        reported_failed = failed_count

    for i, data_row in enumerate(rows):
        state: Dict[str, Any] = {"row_index": data_row.row_index}
        row_failed = False
        row_result: Dict[str, Any] = {}

        for step in plan.steps:
            if circuit_registry and await circuit_registry.is_open(step.canonical_key):
                row_failed = True
                row_errors.append({
                    "row_index": data_row.row_index,
                    "step": step.canonical_key,
                    "error": "Circuit breaker open — endpoint temporarily unavailable",
                    "status_code": None,
                })
                break

            if await should_skip_due_to_idempotency(
                db=db,
                workflow_name=plan.workflow_name,
                endpoint_key=step.canonical_key,
                org_id=org_id,
                business_fields=data_row.normalized_data,
            ):
                continue

            # field_sources (provenance per field) intentionally unused here —
            # app/automation/batch_processor.py's stale-update-field guard
            # isn't wired into the bulk pipeline yet (different retry/
            # idempotency semantics, out of scope for now).
            payload, _field_sources = map_payload_for_step(
                step=step,
                input_row=data_row.normalized_data,
                state=state,
            )

            result = await execute_step(
                step=step,
                payload=payload,
                state=state,
                client=client,
                base_url=base_url,
                auth_headers=auth_headers,
                dry_run=dry_run,
            )

            db.add(AutomationStepLog(
                automation_run_id=automation_run_id,
                step_order=step.order,
                method=step.method,
                path=step.path,
                status=result.status,
                status_code=result.status_code,
                # Sanitize before persisting — removes auth headers, tokens, passwords
                request_payload=sanitize_payload(result.request_payload),
                response_payload=(
                    result.response_payload
                    if isinstance(result.response_payload, dict)
                    else {"value": str(result.response_payload)}
                ),
                error_message=result.error_message,
            ))

            row_result[step.canonical_key] = result.model_dump()

            if result.status in {"success", "dry_run"}:
                if circuit_registry:
                    await circuit_registry.record_success(step.canonical_key)

                state = update_state_from_response(
                    state=state,
                    response_payload=result.response_payload,
                    action=step.action,
                )

                if not dry_run:
                    await save_success_idempotency(
                        db=db,
                        automation_run_id=automation_run_id,
                        data_row_id=data_row.id,
                        row_index=data_row.row_index,
                        workflow_name=plan.workflow_name,
                        endpoint_key=step.canonical_key,
                        org_id=org_id,
                        business_fields=data_row.normalized_data,
                        response_reference={
                            "status_code": result.status_code,
                            "response_payload": result.response_payload,
                        },
                    )
            else:
                if circuit_registry:
                    await circuit_registry.record_failure(step.canonical_key)

                row_failed = True
                row_errors.append({
                    "row_index": data_row.row_index,
                    "step": step.canonical_key,
                    "error": result.error_message,
                    "status_code": result.status_code,
                })
                break

        if row_failed:
            failed_count += 1
            data_row.status = "failed"
            data_row.error_message = "Execution failed"
        else:
            success_count += 1
            data_row.status = "success" if not dry_run else "dry_run_success"

        db.add(BulkBatchRow(
            batch_id=batch.id,
            data_row_id=data_row.id,
            row_index=data_row.row_index,
            status=data_row.status,
            error_message=data_row.error_message,
            result_json=row_result,
        ))

        # ── Commit intermédiaire toutes les N lignes ──────────────────────────
        # Sans cela, une session sur 10 000 lignes × 3 steps dure > 30 min
        # et PostgreSQL la ferme avec "SSL connection has been closed unexpectedly".
        if (i + 1) % BATCH_COMMIT_SIZE == 0:
            await db.commit()
            _report_progress_delta()

    # ── Finalisation du batch ─────────────────────────────────────────────────
    batch.status = "completed"
    batch.success_count = success_count
    batch.failed_count = failed_count
    batch.metadata_json = {"duration_seconds": round(time.time() - started_at, 3)}

    await db.commit()
    # Report whatever's left since the last intermediate checkpoint (or the
    # whole batch, if it finished before ever hitting BATCH_COMMIT_SIZE rows).
    _report_progress_delta()

    try:
        from app.observability.metrics import record_bulk_batch
        record_bulk_batch(batch.status)
    except Exception:
        pass

    return {
        "batch_id": batch.id,
        "batch_number": batch_number,
        "rows_count": len(rows),
        "success_count": success_count,
        "failed_count": failed_count,
        "errors": row_errors,
    }
