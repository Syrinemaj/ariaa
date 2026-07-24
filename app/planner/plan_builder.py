"""
Plan builder — async SQLAlchemy.

N+1 supprimé (Fix 1.3) : batch load via .in_() + joinedload.
Async (Fix 6.3) : select() + await db.execute().
"""
from __future__ import annotations

import asyncio
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.config import settings
from app.core.logging import get_logger
from app.models.endpoint import Endpoint
# ARIA-WORKFLOW-V2: Phase 4 needs WorkflowModel at runtime (DB lookup below),
# not just for type-checking — no longer guarded by TYPE_CHECKING.
from app.models.workflow import WorkflowModel
from app.planner.models import AutomationPlan, BusinessIntent, PlanStep
from app.planner.plan_generator import FALLBACK_MESSAGE, generate_plan_selection
from app.planner.step_ordering import (
    DependencyCycleError,
    detect_schema_dependencies,
    topological_sort_steps,
)
from app.rag.context_builder import build_rag_context
from app.rag.pipeline import merge_deduplicate, search_rag_context
# ARIA-EVAL: EVAL_MODE=false by default — no-op in production, see
# evaluation/tracer.py.
from evaluation.tracer import EVAL_MODE, get_tracer

logger = get_logger(__name__)

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
    embedding_client=None,
    ai_client=None,
    org_id: Optional[str] = None,
    # ARIA-WORKFLOW-V2: Phase 4 — auto-looked-up below (org_id + primary_entity
    # + action) when left as None. Still overridable by a caller that already
    # has a specific WorkflowModel in hand.
    existing_workflow: "WorkflowModel | None" = None,
    # ARIA-WORKFLOW-V2: BusinessIntent has no csv_columns field (checked
    # app/planner/models.py) — this is its own parameter, same reasoning as
    # generate_plan_selection()'s own csv_columns param in 2B/2D.
    csv_columns: List[str] | None = None,
) -> AutomationPlan:
    """
    embedding_client — an EmbeddingClientProtocol instance (LocalEmbeddingClient).
    Falls back to LocalEmbeddingClient() when not provided (standalone usage).

    ai_client — an AIClientProtocol instance (GroqClient or AzureOpenAIClient).
    # ARIA-RAG-FIX: when provided, the RAG-retrieved candidates are filtered
    # through generate_plan_selection() (app/planner/plan_generator.py)
    # instead of turning every RAG hit into a plan step unconditionally.
    # None (default) preserves the previous behaviour for callers/tests that
    # don't pass it.
    """
    # ARIA-EVAL: Phase 8 (evaluation/run_eval.py) found rag_triggered=True
    # on every category-C (garbage instruction) golden case — RAG and
    # generate_plan_selection() ran to completion for instructions that
    # app/api/automation.py:310 rejects anyway right after, once confidence
    # is known. Same threshold (settings.PLAN_MIN_INTENT_CONFIDENCE) reused
    # here rather than a second, lower one — a second threshold would only
    # early-exit below it, leaving the [new_threshold, 0.4) band still
    # running RAG/LLM for nothing before being rejected downstream anyway.
    if intent.confidence < settings.PLAN_MIN_INTENT_CONFIDENCE:
        return AutomationPlan(
            run_id=run_id,
            instruction=instruction,
            intent=intent,
            workflow_name="rejected_low_confidence",
            steps=[],
            requires_approval=False,
            dry_run_default=True,
            metadata={
                "skip_reason": "intent_confidence_too_low",
                "rag_context": "RAG non exécuté : confidence de l'intention insuffisante.",
            },
        )

    if embedding_client is None:
        from app.rag.embeddings.client import LocalEmbeddingClient
        embedding_client = LocalEmbeddingClient()

    # ARIA-WORKFLOW-V2: BusinessIntent has no singular "entity" field (checked
    # app/planner/models.py — only "entities: List[str]"). Using the first
    # entity as the "primary entity" stand-in, falling back to business_domain.
    primary_entity = intent.entities[0] if intent.entities else (intent.business_domain or "")

    # ARIA-WORKFLOW-V2: Phase 4 — automatic WorkflowModel lookup. Real fields
    # are org_id/primary_entity/action (migration 013,
    # alembic/versions/013_workflow_entity_action_org.py); the original spec's
    # WorkflowModel.confidence_score doesn't exist, corrected to .confidence
    # (same fix as Phase 1). NOTE: primary_entity/action are NULL on every
    # existing WorkflowModel row — nothing populates them yet — so in practice
    # this lookup always returns None today. Wired in now so it activates for
    # free once a future enrichment step backfills those columns. Skipped
    # entirely if the caller already passed an explicit existing_workflow.
    if existing_workflow is None and org_id is not None:
        workflow_lookup = await db.execute(
            select(WorkflowModel)
            .where(
                WorkflowModel.org_id == org_id,
                WorkflowModel.primary_entity == primary_entity,
                WorkflowModel.action == intent.action,
            )
            .order_by(WorkflowModel.confidence.desc())
            .limit(1)
        )
        existing_workflow = workflow_lookup.scalar_one_or_none()

    # ARIA-WORKFLOW-V2: query_1 targets the instruction's direct intent;
    # query_2 targets implicit dependency endpoints (setup/assign/notify)
    # that a single query tends to under-rank. Run both in parallel and
    # merge_deduplicate() (app/rag/pipeline.py) so the same endpoint scored
    # by both queries only counts once, keeping its best score.
    query_1 = " ".join(filter(None, [
        instruction,
        intent.action,
        primary_entity,
        " ".join(intent.entities),
        intent.business_domain or "",
    ])).strip()
    query_2 = f"{primary_entity} setup configuration assign notify contract"

    (results_1, _context_1), (results_2, _context_2) = await asyncio.gather(
        search_rag_context(
            db=db,
            query=query_1,
            client=embedding_client,
            run_id=run_id,
            org_id=org_id,
            top_k=5,
            # Without a floor, semantic search always returns the top_k
            # "closest" endpoints even when none are actually relevant to
            # the instruction — this filters those out instead of silently
            # building a garbage plan.
            score_threshold=settings.PLAN_MIN_RAG_SCORE,
        ),
        search_rag_context(
            db=db,
            query=query_2,
            client=embedding_client,
            run_id=run_id,
            org_id=org_id,
            top_k=3,
            score_threshold=settings.PLAN_MIN_RAG_SCORE,
        ),
    )

    search_results = merge_deduplicate(results_1, results_2)
    context = build_rag_context(search_results)
    # ARIA-EVAL: search_rag_context() runs twice here (double query, see
    # above), so there's no single query/results/context to trace at "the"
    # RAG step — query_1 (the instruction's direct intent) is recorded as
    # the representative query, and search_results/context are the merged,
    # deduplicated post-both-queries values actually used downstream, not
    # either query's own raw output.
    if EVAL_MODE and (t := get_tracer()):
        t.record_rag(query_1, search_results, context)

    # ARIA-RAG-FIX: rag_context was computed above but never read by an LLM
    # to decide which retrieved endpoints are actually relevant — every RAG
    # hit became a plan step unconditionally. This closes that gap.
    # ARIA-WORKFLOW-V2: generate_plan_selection() now returns the full
    # structured dict (steps/reasoning/missing_endpoints/confidence), not
    # just the key list — consumed below and surfaced in plan.metadata.
    plan_metadata: dict = {}
    # ARIA-EVAL: initialized here (not just inside the `if ai_client` branch)
    # so the tracer call below can safely reference it even when ai_client is
    # None — previously undefined in that branch, which would have raised
    # NameError the first time EVAL_MODE actually ran without an ai_client.
    plan_result: Optional[Dict] = None
    if ai_client is not None:
        plan_result = generate_plan_selection(
            instruction=instruction,
            rag_context=context,
            client=ai_client,
            intent=intent,
            existing_workflow=existing_workflow,
            csv_columns=csv_columns,
        )
        if plan_result is not None:
            selected_keys = plan_result.get("selected_canonical_keys", [])
            # Never trust LLM-returned keys blindly — keep only those that
            # were actually present in the RAG candidate set (grounding).
            candidates_by_key = {r.canonical_key: r for r in search_results}
            search_results = [
                candidates_by_key[key] for key in selected_keys if key in candidates_by_key
            ]
            plan_metadata = {
                "reasoning": plan_result.get("reasoning"),
                "missing_endpoints": plan_result.get("missing_endpoints", []),
                "plan_confidence": plan_result.get("confidence", 0.0),
                "steps_detail": plan_result.get("steps", []),
            }

    # ARIA-EVAL: passing plan_result["steps"] (raw LLM dicts, each with a
    # "loop" key) rather than the PlanStep list built further down — PlanStep
    # (app/planner/models.py) has no `loop` field, only `field_mapping`, so
    # has_loop would always read False if given PlanStep objects instead.
    if EVAL_MODE and (t := get_tracer()):
        t.record_plan(plan_result, plan_result.get("steps", []) if plan_result else [])

    # ARIA-RAG-FIX: surface an explicit message instead of a silent empty
    # string in plan.metadata when nothing was retrieved.
    rag_context_display = context or FALLBACK_MESSAGE

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

    # ARIA-WORKFLOW-V2: populate each step's field_mapping from the LLM's
    # steps_detail (plan_metadata, set above), matched by canonical_key.
    # Empty dict (PlanStep's default) when generate_plan_selection() wasn't
    # called, fell back to None, or didn't map this particular step.
    field_mapping_by_key = {
        s["canonical_key"]: s.get("field_mapping", {})
        for s in plan_metadata.get("steps_detail", [])
        if "canonical_key" in s
    }
    for step in steps:
        if step.canonical_key in field_mapping_by_key:
            step.field_mapping = field_mapping_by_key[step.canonical_key]

    # RAG ranks by semantic relevance, not execution order — a step that
    # creates a resource can easily score lower than one that references it.
    # Detect real create-then-reference dependencies from response/path
    # schemas and reorder so execution order is actually safe.
    step_dicts = [s.model_dump() for s in steps]
    detect_schema_dependencies(step_dicts)
    try:
        step_dicts = topological_sort_steps(step_dicts)
    except DependencyCycleError as exc:
        logger.warning("plan_builder.dependency_cycle", run_id=run_id, error=str(exc))
    steps = [PlanStep(**d) for d in step_dicts]

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
            "rag_context": rag_context_display,
            "retrieved_endpoints": len(steps),
            **plan_metadata,  # ARIA-WORKFLOW-V2: reasoning, missing_endpoints, plan_confidence, steps_detail
        },
    )
