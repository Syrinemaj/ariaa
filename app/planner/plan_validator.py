from typing import List

from sqlalchemy.orm import Session

from app.models.endpoint import Endpoint
from app.planner.models import AutomationPlan, PlanValidationIssue, PlanValidationResult


FORBIDDEN_METHODS_BY_DEFAULT = {"DELETE"}


def validate_plan(
    db: Session,
    plan: AutomationPlan,
    allow_delete: bool = False,
) -> PlanValidationResult:
    issues: List[PlanValidationIssue] = []

    if not plan.steps:
        issues.append(PlanValidationIssue(
            level="error",
            message="No endpoints found for this instruction.",
        ))

    for step in plan.steps:
        endpoint = db.query(Endpoint).filter(Endpoint.id == step.endpoint_id).first()

        if not endpoint:
            issues.append(PlanValidationIssue(
                level="error",
                message="Endpoint does not exist in registry.",
                step_order=step.order,
                canonical_key=step.canonical_key,
            ))
            continue

        if step.method.upper() in FORBIDDEN_METHODS_BY_DEFAULT and not allow_delete:
            issues.append(PlanValidationIssue(
                level="error",
                message="DELETE method is forbidden by default.",
                step_order=step.order,
                canonical_key=step.canonical_key,
            ))

        if step.auth_required:
            issues.append(PlanValidationIssue(
                level="warning",
                message="Endpoint requires authentication. Auth headers must be provided at execution time.",
                step_order=step.order,
                canonical_key=step.canonical_key,
            ))

        if step.risk_level in {"medium", "high"}:
            issues.append(PlanValidationIssue(
                level="warning",
                message=f"Step risk level is {step.risk_level}. Approval recommended.",
                step_order=step.order,
                canonical_key=step.canonical_key,
            ))

    has_error = any(issue.level == "error" for issue in issues)
    return PlanValidationResult(is_valid=not has_error, issues=issues)
