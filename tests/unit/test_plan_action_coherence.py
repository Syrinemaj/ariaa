"""Action-substitution guard: a write request must be served by a matching HTTP method."""
import pytest

from app.planner.models import AutomationPlan, BusinessIntent, PlanStep
from app.planner.plan_validator import check_action_coherence


def make_plan(action: str, methods: list[str]) -> AutomationPlan:
    steps = [
        PlanStep(
            order=i,
            endpoint_id=f"ep-{i}",
            method=m,
            path=f"/api/step{i}",
            canonical_key=f"{m} /api/step{i}",
        )
        for i, m in enumerate(methods, start=1)
    ]
    return AutomationPlan(
        run_id="run-test",
        instruction="test",
        intent=BusinessIntent(instruction="test", intent="test", action=action, confidence=0.9),
        workflow_name="wf",
        steps=steps,
    )


def test_delete_request_served_by_reads_only_is_rejected():
    # Scenario S3: "delete a user" answered by GET current user + GET logout.
    issue = check_action_coherence(make_plan("delete", ["GET", "GET"]))
    assert issue is not None
    assert issue.level == "error"
    assert "ACTION_NOT_AVAILABLE" in issue.message


def test_delete_request_with_delete_step_is_accepted():
    assert check_action_coherence(make_plan("delete", ["GET", "DELETE"])) is None


@pytest.mark.parametrize("action,methods", [
    ("create", ["POST"]),
    ("update", ["PATCH"]),
    ("update", ["POST"]),
])
def test_write_request_with_matching_method_is_accepted(action, methods):
    assert check_action_coherence(make_plan(action, methods)) is None


@pytest.mark.parametrize("action", ["create", "update"])
def test_write_request_served_by_reads_only_is_rejected(action):
    assert check_action_coherence(make_plan(action, ["GET"])) is not None


@pytest.mark.parametrize("action", ["fetch", "list", "authenticate", "other", "send"])
def test_non_write_actions_are_not_checked(action):
    assert check_action_coherence(make_plan(action, ["GET"])) is None


def test_action_case_is_ignored():
    assert check_action_coherence(make_plan("DELETE", ["GET"])) is not None


def test_empty_plan_is_left_to_other_checks():
    assert check_action_coherence(make_plan("delete", [])) is None
