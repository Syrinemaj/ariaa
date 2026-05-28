from app.planner.models import AutomationPlan


FORBIDDEN_METHODS = {"DELETE"}
HIGH_RISK_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class ExecutionGuardError(Exception):
    pass


def assert_execution_allowed(
    plan: AutomationPlan,
    dry_run: bool = True,
    allow_delete: bool = False,
    approval_granted: bool = False,
) -> None:
    if dry_run:
        return

    if plan.requires_approval and not approval_granted:
        raise ExecutionGuardError("Real execution requires explicit approval.")

    for step in plan.steps:
        method = step.method.upper()

        if method in FORBIDDEN_METHODS and not allow_delete:
            raise ExecutionGuardError(
                f"Method {method} is forbidden by default for {step.canonical_key}."
            )

        if method in HIGH_RISK_METHODS and not approval_granted:
            raise ExecutionGuardError(
                f"High-risk method {method} requires approval for {step.canonical_key}."
            )
