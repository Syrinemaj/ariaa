from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.endpoint import Endpoint
from app.planner.models import AutomationPlan, PlanValidationIssue, PlanValidationResult
from app.planner.step_ordering import DependencyCycleError, topological_sort_steps


FORBIDDEN_METHODS_BY_DEFAULT = {"DELETE"}

# Write intents and the HTTP methods able to fulfil them. Read-only intents
# (fetch, list, authenticate, other...) are not checked: any method may serve
# them. Guards against "action substitution" — e.g. a delete request answered
# by a GET + logout plan because the catalogue has no DELETE endpoint, which
# would then pass governance as a harmless read-only plan.
ACTION_REQUIRED_METHODS = {
    "delete": {"DELETE"},
    "create": {"POST", "PUT"},
    "update": {"PUT", "PATCH", "POST"},
}

ACTION_COHERENCE_CODE = "ACTION_NOT_AVAILABLE"


def check_action_coherence(plan: AutomationPlan) -> Optional[PlanValidationIssue]:
    """Returns an error issue when the requested write action is performed
    by none of the plan's steps, None otherwise."""
    if not plan.intent or not plan.steps:
        return None
    action = (plan.intent.action or "").strip().lower()
    required = ACTION_REQUIRED_METHODS.get(action)
    if not required:
        return None
    methods = {step.method.upper() for step in plan.steps}
    if methods & required:
        return None
    return PlanValidationIssue(
        level="error",
        message=(
            f"{ACTION_COHERENCE_CODE}: the requested action '{action}' requires "
            f"one of {sorted(required)}, but the plan only uses {sorted(methods)}."
        ),
    )


def _validate_dependencies(plan: AutomationPlan) -> List[PlanValidationIssue]:
    """
    Two things a broken depends_on can do: point at a step that isn't in
    this plan (dangling — e.g. RAG's score threshold filtered the producer
    step out), or form a cycle. Both would make the plan unsafe to execute
    in its stated order, so both are hard errors, not warnings.
    """
    issues: List[PlanValidationIssue] = []
    canonical_keys = {step.canonical_key for step in plan.steps}

    for step in plan.steps:
        for dep in step.depends_on:
            if dep not in canonical_keys:
                issues.append(PlanValidationIssue(
                    level="error",
                    message=f"Step depends on {dep!r}, which is not part of this plan.",
                    step_order=step.order,
                    canonical_key=step.canonical_key,
                ))

    try:
        topological_sort_steps([s.model_dump() for s in plan.steps])
    except DependencyCycleError as exc:
        issues.append(PlanValidationIssue(
            level="error",
            message=f"Circular dependency among plan steps: {exc}",
        ))

    return issues


async def validate_plan(
    db: AsyncSession,
    plan: AutomationPlan,
    allow_delete: bool = False,
) -> PlanValidationResult:
    issues: List[PlanValidationIssue] = []

    if not plan.steps:
        issues.append(PlanValidationIssue(
            level="error",
            message="No endpoints found for this instruction.",
        ))

    issues.extend(_validate_dependencies(plan))

    coherence_issue = check_action_coherence(plan)
    if coherence_issue:
        issues.append(coherence_issue)

    for step in plan.steps:
        result = await db.execute(
            select(Endpoint).where(Endpoint.id == step.endpoint_id)
        )
        endpoint = result.scalar_one_or_none()

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
