from typing import Tuple

from sqlalchemy.orm import Session

from app.planner.intent_analyzer import analyze_business_intent
from app.planner.models import AutomationPlan, PlanValidationResult
from app.planner.plan_builder import build_automation_plan
from app.planner.plan_validator import validate_plan


def create_plan_from_instruction(
    db: Session,
    run_id: str,
    instruction: str,
    top_k: int = 8,
) -> Tuple[AutomationPlan, PlanValidationResult]:
    intent = analyze_business_intent(instruction)

    plan = build_automation_plan(
        db=db,
        run_id=run_id,
        instruction=instruction,
        intent=intent,
        top_k=top_k,
    )

    validation = validate_plan(db=db, plan=plan)

    return plan, validation
