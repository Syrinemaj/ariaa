"""
Plan builder — async SQLAlchemy.

N+1 supprimé (Fix 1.3) : batch load via .in_() + joinedload.
Async (Fix 6.3) : select() + await db.execute().
"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.endpoint import Endpoint
from app.planner.models import AutomationPlan, BusinessIntent, PlanStep
from app.rag.service import search_rag_context

DANGEROUS_METHODS = {"DELETE"}


def _risk_level(method: str, quantity: Optional[int] = None) -> str:
    method = method.upper()
    if method in DANGEROUS_METHODS:
        return "high"
    if quantity and quantity > 100:
        return "medium"
    if method in {"POST", "PUT", "PATCH"}:
        return "medium"
    return "low"


async def build_automation_plan(
    db: AsyncSession,
    run_id: str,
    instruction: str,
    intent: BusinessIntent,
    top_k: int = 8,
) -> AutomationPlan:
    query = " ".join([
        instruction,
        intent.intent,
        intent.business_domain or "",
        " ".join(intent.entities),
        intent.action,
    ])

    search_results, context = await search_rag_context(
        db=db,
        query=query,
        run_id=run_id,
        top_k=top_k,
    )

    endpoint_ids = [r.endpoint_id for r in search_results]

    result = await db.execute(
        select(Endpoint)
        .options(joinedload(Endpoint.schema))
        .where(Endpoint.id.in_(endpoint_ids))
    )
    endpoints_by_id: dict[str, Endpoint] = {
        ep.id: ep for ep in result.scalars().unique().all()
    }

    steps: List[PlanStep] = []
    for index, search_result in enumerate(search_results, start=1):
        endpoint = endpoints_by_id.get(search_result.endpoint_id)
        if not endpoint:
            continue

        schema = endpoint.schema
        steps.append(PlanStep(
            order=index,
            endpoint_id=endpoint.id,
            method=endpoint.method,
            path=endpoint.path,
            canonical_key=endpoint.canonical_key,
            action=endpoint.business_action,
            business_domain=endpoint.business_domain,
            request_schema=schema.request_schema if schema else None,
            response_schema=schema.response_schema if schema else None,
            auth_required=schema.auth_required if schema else False,
            risk_level=_risk_level(endpoint.method, intent.quantity),
        ))

    requires_approval = (
        intent.requires_bulk_execution
        or any(step.risk_level in {"medium", "high"} for step in steps)
    )

    return AutomationPlan(
        run_id=run_id,
        instruction=instruction,
        intent=intent,
        workflow_name=intent.intent or "generated_automation_plan",
        steps=steps,
        requires_approval=requires_approval,
        dry_run_default=True,
        metadata={
            "rag_context": context,
            "retrieved_endpoints": len(steps),
        },
    )
