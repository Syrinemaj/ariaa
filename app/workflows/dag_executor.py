"""
DAG-aware execution engine.

Replaces the sequential step loop in automation/service.py.
Each parallel group from WorkflowDAG is executed via asyncio.gather,
reducing total wall-clock time for independent steps.

State propagation: each completed step's response dict is merged into
`state` so downstream steps can reference upstream outputs by field name
(e.g. {employee_id} resolved from a prior POST /employees response).
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

import httpx

from app.automation.executor import StepExecutionResult, execute_step
from app.planner.models import PlanStep
from app.workflows.dag_builder import WorkflowDAG


async def execute_dag(
    dag: WorkflowDAG,
    steps_by_key: Dict[str, PlanStep],
    payload: Dict[str, Any],
    state: Dict[str, Any],
    client: httpx.AsyncClient,
    base_url: Optional[str] = None,
    auth_headers: Optional[Dict[str, str]] = None,
    dry_run: bool = True,
) -> List[StepExecutionResult]:
    """
    Execute all DAG steps in dependency order, with intra-group parallelism.

    Groups are processed sequentially (a group only starts when the prior
    group finishes). Within each group, asyncio.gather runs all steps
    concurrently on the same event loop thread.

    Args:
        dag:           Pre-built WorkflowDAG (call WorkflowDAG.from_endpoints).
        steps_by_key:  Mapping from canonical_key → PlanStep.
        payload:       Input data for the first step (e.g. user-provided values).
        state:         Mutable execution context shared across all steps.
        client:        Shared httpx.AsyncClient (one per run, not per step).
        base_url:      Target API base URL.
        auth_headers:  Auth headers forwarded to every request.
        dry_run:       If True, no real HTTP calls are made.

    Returns:
        Flat list of StepExecutionResult in execution order.
    """
    all_results: List[StepExecutionResult] = []

    for parallel_group in dag.topological_sort():
        group_results: List[StepExecutionResult] = await asyncio.gather(*[
            execute_step(
                step=steps_by_key[node_id],
                payload=payload,
                state=dict(state),  # snapshot to avoid mid-group mutation
                client=client,
                base_url=base_url,
                auth_headers=auth_headers,
                dry_run=dry_run,
            )
            for node_id in parallel_group
            if node_id in steps_by_key
        ])

        for result in group_results:
            all_results.append(result)
            # Merge successful responses into shared state for downstream steps
            if (
                result.status == "success"
                and isinstance(result.response_payload, dict)
            ):
                state.update(result.response_payload)

    return all_results
