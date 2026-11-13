from app.governance.scoring import compute_plan_risk_score, step_risk_score
from app.planner.models import AutomationPlan, BusinessIntent, PlanStep


def _step(risk_level: str, order: int = 1) -> PlanStep:
    return PlanStep(
        order=order,
        endpoint_id=f"ep-{order}",
        method="GET",
        path="/things",
        canonical_key=f"GET /things#{order}",
        risk_level=risk_level,
    )


def _plan(steps) -> AutomationPlan:
    return AutomationPlan(
        run_id="run-1",
        instruction="do the thing",
        intent=BusinessIntent(instruction="do the thing", intent="x", action="x"),
        workflow_name="wf",
        steps=steps,
    )


def test_step_risk_score_known_levels():
    assert step_risk_score("low") == 1
    assert step_risk_score("medium") == 5
    assert step_risk_score("high") == 10


def test_step_risk_score_unknown_level_fails_closed():
    assert step_risk_score("unexpected") == 10


def test_plan_score_is_max_of_steps():
    plan = _plan([_step("low", 1), _step("high", 2), _step("medium", 3)])
    assert compute_plan_risk_score(plan) == 10


def test_plan_score_all_low():
    plan = _plan([_step("low", 1), _step("low", 2)])
    assert compute_plan_risk_score(plan) == 1


def test_plan_score_no_steps_defaults_to_low():
    plan = _plan([])
    assert compute_plan_risk_score(plan) == 1
