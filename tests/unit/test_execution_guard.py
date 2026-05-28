import pytest
from app.security.execution_guard import assert_execution_allowed, ExecutionGuardError
from app.planner.models import AutomationPlan, BusinessIntent, PlanStep


def make_intent():
    return BusinessIntent(
        instruction="test",
        intent="list",
        action="list",
        confidence=0.9,
    )


def make_plan(requires_approval: bool = True, methods: list = None) -> AutomationPlan:
    steps = []
    for i, method in enumerate(methods or ["GET"], start=1):
        steps.append(
            PlanStep(
                order=i,
                endpoint_id=f"ep-{i}",
                method=method,
                path="/api/users",
                canonical_key=f"{method} /api/users",
            )
        )
    return AutomationPlan(
        run_id="run-test",
        instruction="test",
        intent=make_intent(),
        workflow_name="test-workflow",
        steps=steps,
        requires_approval=requires_approval,
    )


class TestDryRun:
    def test_dry_run_always_passes(self):
        plan = make_plan(requires_approval=True, methods=["DELETE"])
        assert_execution_allowed(plan, dry_run=True)

    def test_dry_run_passes_without_approval(self):
        plan = make_plan(requires_approval=True, methods=["POST"])
        assert_execution_allowed(plan, dry_run=True, approval_granted=False)


class TestRealExecution:
    def test_requires_approval_without_grant_raises(self):
        plan = make_plan(requires_approval=True, methods=["GET"])
        with pytest.raises(ExecutionGuardError, match="approval"):
            assert_execution_allowed(plan, dry_run=False, approval_granted=False)

    def test_delete_without_allow_delete_raises(self):
        plan = make_plan(requires_approval=False, methods=["DELETE"])
        with pytest.raises(ExecutionGuardError, match="forbidden"):
            assert_execution_allowed(
                plan, dry_run=False, allow_delete=False, approval_granted=True
            )

    def test_delete_with_allow_delete_raises_high_risk(self):
        plan = make_plan(requires_approval=False, methods=["DELETE"])
        with pytest.raises(ExecutionGuardError):
            assert_execution_allowed(
                plan, dry_run=False, allow_delete=True, approval_granted=False
            )

    def test_post_without_approval_raises(self):
        plan = make_plan(requires_approval=False, methods=["POST"])
        with pytest.raises(ExecutionGuardError, match="High-risk"):
            assert_execution_allowed(plan, dry_run=False, approval_granted=False)

    def test_get_with_approval_passes(self):
        plan = make_plan(requires_approval=False, methods=["GET"])
        assert_execution_allowed(plan, dry_run=False, approval_granted=True)

    def test_post_with_approval_passes(self):
        plan = make_plan(requires_approval=False, methods=["POST"])
        assert_execution_allowed(plan, dry_run=False, approval_granted=True)
