"""Numeric risk score for an AutomationPlan.

No numeric risk score existed before this feature — PlanStep.risk_level is a
heuristic low/medium/high string (app/planner/plan_builder.py::_risk_level),
disconnected from governance thresholds. This maps that string onto a number
so GovernancePolicy.risk_threshold_low/high (plain ints) can be compared
against it.
"""
from app.planner.models import AutomationPlan

RISK_LEVEL_SCORES = {"low": 1, "medium": 5, "high": 10}

# A step whose risk_level isn't one of the three known values (shouldn't
# happen — _risk_level only ever returns one of them) scores as the most
# severe, so an unrecognized value fails closed rather than silently ALLOWing.
_UNKNOWN_RISK_SCORE = RISK_LEVEL_SCORES["high"]


def step_risk_score(risk_level: str) -> int:
    return RISK_LEVEL_SCORES.get(risk_level, _UNKNOWN_RISK_SCORE)


def compute_plan_risk_score(plan: AutomationPlan) -> int:
    """Plan score = max(step scores) — one high-risk step makes the whole
    plan high-risk; it is not diluted by averaging against low-risk steps."""
    if not plan.steps:
        return RISK_LEVEL_SCORES["low"]
    return max(step_risk_score(step.risk_level) for step in plan.steps)
