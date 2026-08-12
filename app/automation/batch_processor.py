"""
Simple (non-bulk) plan execution — creates ONE httpx client per run.

This module handles the lightweight /automation/execute route.
For large-scale execution (thousands of rows), use the Celery pipeline
via /bulk/execute → workers/tasks/execution.py.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from app.automation.executor import execute_step
from app.automation.models import AutomationExecutionResult, StepExecutionResult
from app.automation.payload_mapper import map_payload_for_step
from app.automation.rate_limiter import SimpleRateLimiter
from app.automation.retry_manager import with_retries
from app.automation.state_manager import update_state_from_response
from app.planner.models import AutomationPlan, PlanStep
from app.security.ssrf_guard import SSRFError, create_safe_client

# Methods that modify an existing resource — a required body field on one of
# these whose only source is a prior step's response (never the row data or
# an explicit plan mapping) is almost always a no-op write-back rather than
# an intentional update, since nothing in the run ever said what the NEW
# value should be. Diagnosed from a real case: an "approve type=congé, leave
# the rest pending" instruction silently PATCHed every row's status back to
# whatever the create step had just set, because no field_mapping or row
# data ever specified the target status per row (see payload_mapper.py).
_UPDATE_METHODS = {"PATCH", "PUT", "DELETE"}


def _check_stale_update_fields(step: PlanStep, field_sources: Dict[str, str]) -> List[str]:
    """
    Two suspicious cases for a PATCH/PUT/DELETE body field, both meaning "no
    one ever actually decided what this field's new value should be":

    - source == "state": the value was echoed back verbatim from a previous
      step's response for this row — real-execution case (state only holds
      real data once a real call already ran; see the diagnosed bug).
    - required field missing from field_sources entirely: not resolvable
      from the row, plan mapping, OR state — this is the ONLY signal
      available in dry_run, since state never holds real response data
      there (execute_step returns a canned message without calling out).
      Also relevant in real execution as an earlier, more specific error
      than the generic jsonschema failure assert_payload_valid would raise
      downstream.
    """
    if step.method.upper() not in _UPDATE_METHODS:
        return []

    required = (step.request_schema or {}).get("required", [])
    stale = sorted(f for f, source in field_sources.items() if source == "state")
    unresolved = sorted(f for f in required if f not in field_sources)

    warnings: List[str] = []
    if stale:
        fields_list = ", ".join(stale)
        warnings.append(
            f"{step.method} {step.path} : le(s) champ(s) '{fields_list}' "
            "sont repris tels quels depuis la réponse d'une étape précédente — "
            "aucune donnée de ligne ni règle de plan ne fournit de valeur cible "
            "explicite, cette mise à jour va probablement réécrire la valeur "
            f"déjà en place. Ajoutez '{fields_list}' explicitement dans vos "
            "données de ligne, ou dans le field_mapping du plan si la valeur "
            "dépend d'une autre colonne (ex: statut selon le type)."
        )
    if unresolved:
        fields_list = ", ".join(unresolved)
        warnings.append(
            f"{step.method} {step.path} : le(s) champ(s) requis '{fields_list}' "
            "ne sont trouvables ni dans vos données de ligne, ni dans le "
            "field_mapping du plan. Ajoutez-les explicitement."
        )
    return warnings


async def execute_plan_batch(
    plan: AutomationPlan,
    input_rows: List[Dict[str, Any]],
    base_url: Optional[str] = None,
    auth_headers: Optional[Dict[str, str]] = None,
    dry_run: bool = True,
) -> AutomationExecutionResult:
    """
    Execute an automation plan against a list of input rows.

    ONE httpx.AsyncClient is created for the ENTIRE run (not per row, not per
    step). This preserves TCP keep-alive connections and respects the target
    API's connection limits.

    For dry_run=True, no client is needed — all steps return immediately.
    """
    started_at = time.time()
    results: List[StepExecutionResult] = []
    rows = input_rows or [{}]
    limiter = SimpleRateLimiter(delay_seconds=0.1)

    async def _run_with_client(client):
        for row_index, input_row in enumerate(rows):
            row_state: Dict[str, Any] = {"row_index": row_index}

            for step in plan.steps:
                await limiter.wait()

                payload, field_sources = map_payload_for_step(
                    step=step, input_row=input_row, state=row_state
                )
                stale_field_warnings = _check_stale_update_fields(step, field_sources)

                if stale_field_warnings and not dry_run:
                    # Real write, and we can already prove (statically, from
                    # where each value came from) that this step would just
                    # echo back state instead of applying an intended change
                    # — refuse the call rather than send it and report a
                    # misleading 200 OK "success". dry_run keeps going (see
                    # below) so the issue surfaces during preview instead.
                    step_result = StepExecutionResult(
                        step_order=step.order, method=step.method, path=step.path,
                        url=step.path, status="failed", status_code=None,
                        request_payload=payload, response_payload=None,
                        error_message="; ".join(stale_field_warnings),
                        warnings=stale_field_warnings,
                    )
                else:
                    async def operation(s=step, p=payload, rs=row_state):
                        return await execute_step(
                            step=s,
                            payload=p,
                            state=rs,
                            client=client,
                            base_url=base_url,
                            auth_headers=auth_headers,
                            dry_run=dry_run,
                        )

                    step_result = await with_retries(
                        operation=operation,
                        retries=1 if dry_run else 3,
                    )
                    if stale_field_warnings:
                        step_result.warnings = stale_field_warnings

                results.append(step_result)

                if step_result.status in {"success", "dry_run"}:
                    row_state = update_state_from_response(
                        state=row_state,
                        response_payload=step_result.response_payload,
                    )

                if step_result.status == "failed":
                    break

    if dry_run or not base_url:
        # Dry-run mode: execute_step returns early without network I/O.
        # Create a dummy client (it won't be used).
        import httpx
        async with httpx.AsyncClient() as client:
            await _run_with_client(client)
    else:
        # Real execution: create one pinned-DNS client for the whole run.
        try:
            async with create_safe_client(base_url) as client:
                await _run_with_client(client)
        except SSRFError as exc:
            return AutomationExecutionResult(
                status="failed",
                dry_run=dry_run,
                total_steps=0,
                success_count=0,
                failed_count=len(rows),
                results=[],
                metadata={"error": str(exc)},
            )

    success_count = sum(1 for r in results if r.status in {"success", "dry_run"})
    failed_count = sum(1 for r in results if r.status == "failed")

    return AutomationExecutionResult(
        status="success" if failed_count == 0 else "partial_failure",
        dry_run=dry_run,
        total_steps=len(results),
        success_count=success_count,
        failed_count=failed_count,
        results=results,
        metadata={
            "duration_seconds": round(time.time() - started_at, 3),
            "rows_count": len(rows),
            "workflow_name": plan.workflow_name,
        },
    )
