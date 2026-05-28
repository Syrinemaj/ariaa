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
from app.planner.models import AutomationPlan
from app.security.ssrf_guard import SSRFError, create_safe_client


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

                payload = map_payload_for_step(
                    step=step, input_row=input_row, state=row_state
                )

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
