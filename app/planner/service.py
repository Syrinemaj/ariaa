from typing import TYPE_CHECKING, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.endpoint import Endpoint
from app.planner.intent_analyzer import analyze_business_intent
from app.planner.models import AutomationPlan, PlanValidationResult
from app.planner.plan_builder import build_automation_plan
from app.planner.plan_validator import validate_plan
# ARIA-EVAL: EVAL_MODE=false by default (evaluation/tracer.py) — every call
# below is a no-op in production; get_tracer() returns None unless the
# EVAL_MODE env var is set, so `if EVAL_MODE and (t := get_tracer())` never
# executes.
from evaluation.tracer import EVAL_MODE, get_tracer, reset_tracer

if TYPE_CHECKING:
    from app.models.workflow import WorkflowModel


async def _get_known_domains(db: AsyncSession, run_id: str) -> list[str]:
    """Distinct business domains already discovered for this run — used to
    ground the intent analyzer's domain guess in what actually exists,
    instead of a fixed enum that assumes every API is HR/payroll."""
    result = await db.execute(
        select(Endpoint.business_domain)
        .where(Endpoint.run_id == run_id, Endpoint.business_domain.isnot(None))
        .distinct()
    )
    return sorted({d for (d,) in result.all() if d})


async def create_plan_from_instruction(
    db: AsyncSession,
    run_id: str,
    instruction: str,
    top_k: int = 8,
    embedding_client=None,
    ai_client=None,
    org_id: Optional[str] = None,
    # ARIA-WORKFLOW-V2: passthrough only — the automatic lookup (org_id +
    # primary_entity + action, Phase 4) happens inside build_automation_plan()
    # itself. This lets a caller that already resolved a specific
    # WorkflowModel pass it in directly and skip that lookup.
    existing_workflow: "WorkflowModel | None" = None,
    # ARIA-WORKFLOW-V2: passthrough — no source yet on the API route side
    # (app/api/automation.py's CreatePlanRequest has no csv_columns field),
    # out of scope here per Phase 6; wired through so it's ready once it does.
    csv_columns: List[str] | None = None,
) -> Tuple[AutomationPlan, PlanValidationResult]:
    # ARIA-EVAL: fresh trace per plan-generation call, not per process — a
    # long-lived worker/API process must not leak the previous call's trace
    # into this one.
    if EVAL_MODE:
        reset_tracer()

    known_domains = await _get_known_domains(db, run_id)
    intent = analyze_business_intent(instruction, client=ai_client, known_domains=known_domains)
    if EVAL_MODE and (t := get_tracer()):
        t.record_intent(intent)

    plan = await build_automation_plan(
        db=db,
        run_id=run_id,
        instruction=instruction,
        intent=intent,
        top_k=top_k,
        embedding_client=embedding_client,
        # ARIA-RAG-FIX: was accepted here but never forwarded, so
        # build_automation_plan() never actually received an ai_client to
        # ground its endpoint selection in rag_context.
        ai_client=ai_client,
        org_id=org_id,
        existing_workflow=existing_workflow,
        csv_columns=csv_columns,
    )

    validation = await validate_plan(db=db, plan=plan)
    if EVAL_MODE and (t := get_tracer()):
        t.record_validation(validation)

    return plan, validation
