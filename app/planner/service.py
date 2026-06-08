from typing import Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.planner.intent_analyzer import analyze_business_intent
from app.planner.models import AutomationPlan, PlanValidationResult
from app.planner.plan_builder import build_automation_plan
from app.planner.plan_validator import validate_plan


async def create_plan_from_instruction(
    db: AsyncSession,
    run_id: str,
    instruction: str,
    top_k: int = 8,
    embedding_client=None,
    ai_client=None,
    org_id: Optional[str] = None,
) -> Tuple[AutomationPlan, PlanValidationResult]:
    intent = analyze_business_intent(instruction, client=ai_client)

    plan = await build_automation_plan(
        db=db,
        run_id=run_id,
        instruction=instruction,
        intent=intent,
        top_k=top_k,
        embedding_client=embedding_client,
        org_id=org_id,
    )

    validation = await validate_plan(db=db, plan=plan)

    return plan, validation
