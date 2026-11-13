"""Single policy check every automation plan passes through — at submission
and again right before execution (Phase 1 finding: Bulk Automation currently
has NO such guard at all; Simple Automation only has the narrower hardcoded
app/security/execution_guard.py). Pure function: takes already-fetched
GovernancePolicy + ForbiddenEndpointRule rows, does no DB/network I/O, so it
is trivially testable and callable from both the submit and execute paths
without duplicating logic.

Decision is one of ALLOW / REQUIRE_APPROVAL / BLOCK. A BLOCK can NEVER be
downgraded by admin approval — callers must check `decision == BLOCK` first
and reject outright, before even looking at any approval flag.
"""
from dataclasses import dataclass, field
from fnmatch import fnmatch
from typing import Iterable, List

from app.planner.models import AutomationPlan
from app.governance.scoring import compute_plan_risk_score

ALLOW = "ALLOW"
REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
BLOCK = "BLOCK"

_SEVERITY = {ALLOW: 0, REQUIRE_APPROVAL: 1, BLOCK: 2}

WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


@dataclass
class PolicyResult:
    decision: str
    reasons: List[str] = field(default_factory=list)
    risk_score: int = 0

    @property
    def is_blocked(self) -> bool:
        return self.decision == BLOCK


def _check_forbidden_rules(plan: AutomationPlan, rules: Iterable) -> List[str]:
    reasons = []
    for step in plan.steps:
        method = step.method.upper()
        for rule in rules:
            if rule.method is not None and rule.method.upper() != method:
                continue
            if not fnmatch(step.path, rule.path_pattern):
                continue
            rule_label = f"{rule.method or '*'} {rule.path_pattern}"
            reasons.append(
                f"Forbidden endpoint rule '{rule_label}' matches step "
                f"{method} {step.path} ({step.canonical_key})."
            )
    return reasons


def _check_environment_policy(plan: AutomationPlan, environment: str, environment_policies: dict) -> tuple[str, List[str]]:
    mode = environment_policies.get(environment)

    if mode is None:
        return BLOCK, [f"No environment policy configured for '{environment}' — failing closed."]

    if mode == "forbidden":
        return BLOCK, [f"Environment '{environment}' is forbidden by governance policy."]

    if mode == "full_access":
        return ALLOW, []

    write_steps = [s for s in plan.steps if s.method.upper() in WRITE_METHODS]
    if not write_steps:
        return ALLOW, []

    if mode == "read_only":
        return BLOCK, [
            f"Environment '{environment}' is read-only — plan has "
            f"{len(write_steps)} write step(s) ({', '.join(s.method.upper() for s in write_steps)})."
        ]

    if mode == "writes_require_approval":
        return REQUIRE_APPROVAL, [
            f"Environment '{environment}' requires approval for write steps "
            f"({len(write_steps)} write step(s))."
        ]

    return BLOCK, [f"Unknown environment policy mode '{mode}' for '{environment}' — failing closed."]


def _check_risk_threshold(risk_score: int, risk_threshold_low: int, risk_threshold_high: int) -> tuple[str, List[str]]:
    if risk_score <= risk_threshold_low:
        return ALLOW, []
    if risk_score > risk_threshold_high:
        return BLOCK, [
            f"Plan risk score {risk_score} exceeds the high threshold "
            f"({risk_threshold_high}) — execution blocked."
        ]
    return REQUIRE_APPROVAL, [
        f"Plan risk score {risk_score} is above the low threshold "
        f"({risk_threshold_low}) — admin approval required."
    ]


def check_execution_policy(
    plan: AutomationPlan,
    policy,
    forbidden_rules: Iterable,
    environment: str,
) -> PolicyResult:
    risk_score = compute_plan_risk_score(plan)

    decision = ALLOW
    reasons: List[str] = []

    forbidden_reasons = _check_forbidden_rules(plan, forbidden_rules)
    if forbidden_reasons:
        decision = BLOCK
        reasons.extend(forbidden_reasons)

    env_decision, env_reasons = _check_environment_policy(plan, environment, policy.environment_policies)
    if _SEVERITY[env_decision] > _SEVERITY[decision]:
        decision = env_decision
    reasons.extend(env_reasons)

    risk_decision, risk_reasons = _check_risk_threshold(
        risk_score, policy.risk_threshold_low, policy.risk_threshold_high
    )
    if _SEVERITY[risk_decision] > _SEVERITY[decision]:
        decision = risk_decision
    reasons.extend(risk_reasons)

    return PolicyResult(decision=decision, reasons=reasons, risk_score=risk_score)
