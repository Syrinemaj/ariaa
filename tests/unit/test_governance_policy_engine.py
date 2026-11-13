from types import SimpleNamespace

from app.governance.policy_engine import ALLOW, BLOCK, REQUIRE_APPROVAL, check_execution_policy
from app.models.governance import DEFAULT_ENVIRONMENT_POLICIES
from app.planner.models import AutomationPlan, BusinessIntent, PlanStep


def _step(method: str, path: str, risk_level: str = "low", order: int = 1) -> PlanStep:
    return PlanStep(
        order=order,
        endpoint_id=f"ep-{order}",
        method=method,
        path=path,
        canonical_key=f"{method} {path}#{order}",
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


def _policy(low=1, high=10, env_policies=None):
    return SimpleNamespace(
        risk_threshold_low=low,
        risk_threshold_high=high,
        environment_policies=env_policies or dict(DEFAULT_ENVIRONMENT_POLICIES),
    )


def _rule(method, path_pattern):
    return SimpleNamespace(method=method, path_pattern=path_pattern)


def test_low_risk_plan_in_full_access_env_is_allowed():
    plan = _plan([_step("GET", "/employees", risk_level="low")])
    result = check_execution_policy(plan, _policy(), [], "test")

    assert result.decision == ALLOW
    assert result.reasons == []
    assert result.risk_score == 1


def test_medium_risk_plan_requires_approval():
    plan = _plan([_step("POST", "/absences", risk_level="medium")])
    result = check_execution_policy(plan, _policy(), [], "test")

    assert result.decision == REQUIRE_APPROVAL
    assert result.risk_score == 5
    assert any("risk score" in r for r in result.reasons)


def test_score_above_high_threshold_blocks():
    plan = _plan([_step("DELETE", "/employees/1", risk_level="high")])
    policy = _policy(low=1, high=8)  # high step scores 10 > 8
    result = check_execution_policy(plan, policy, [], "test")

    assert result.decision == BLOCK


def test_forbidden_endpoint_rule_blocks_regardless_of_risk():
    plan = _plan([_step("DELETE", "/employees/42", risk_level="low")])
    rules = [_rule("DELETE", "/employees/*")]
    result = check_execution_policy(plan, _policy(), rules, "test")

    assert result.decision == BLOCK
    assert "Forbidden endpoint rule" in result.reasons[0]
    assert "/employees/*" in result.reasons[0]


def test_forbidden_rule_with_null_method_matches_any_method():
    plan = _plan([_step("GET", "/admin/secrets", risk_level="low")])
    rules = [_rule(None, "/admin/*")]
    result = check_execution_policy(plan, _policy(), rules, "test")

    assert result.decision == BLOCK


def test_forbidden_endpoint_rule_blocks_even_with_approval_context():
    # The caller is expected to check is_blocked BEFORE looking at any
    # approval flag — this test documents that the engine itself never
    # produces anything other than BLOCK once a forbidden rule matches,
    # i.e. there is no parameter that could turn this back into ALLOW.
    plan = _plan([_step("DELETE", "/employees/1", risk_level="low")])
    rules = [_rule("DELETE", "/employees/*")]
    result = check_execution_policy(plan, _policy(low=100, high=200), rules, "test")

    assert result.is_blocked


def test_forbidden_environment_blocks_entirely():
    plan = _plan([_step("GET", "/employees", risk_level="low")])
    policy = _policy(env_policies={"test": "full_access", "preprod": "full_access", "prod": "forbidden"})
    result = check_execution_policy(plan, policy, [], "prod")

    assert result.decision == BLOCK
    assert "forbidden" in result.reasons[0].lower()


def test_read_only_environment_blocks_write_steps():
    plan = _plan([_step("POST", "/absences", risk_level="low")])
    policy = _policy(env_policies={"test": "read_only", "preprod": "full_access", "prod": "full_access"})
    result = check_execution_policy(plan, policy, [], "test")

    assert result.decision == BLOCK


def test_read_only_environment_allows_read_steps():
    plan = _plan([_step("GET", "/absences", risk_level="low")])
    policy = _policy(env_policies={"test": "read_only", "preprod": "full_access", "prod": "full_access"})
    result = check_execution_policy(plan, policy, [], "test")

    assert result.decision == ALLOW


def test_writes_require_approval_environment_flags_write_steps():
    plan = _plan([_step("PUT", "/absences/1", risk_level="low")])
    policy = _policy(env_policies={"test": "writes_require_approval", "preprod": "full_access", "prod": "full_access"})
    result = check_execution_policy(plan, policy, [], "test")

    assert result.decision == REQUIRE_APPROVAL


def test_unknown_environment_fails_closed():
    plan = _plan([_step("GET", "/employees", risk_level="low")])
    result = check_execution_policy(plan, _policy(), [], "staging")

    assert result.decision == BLOCK


def test_multiple_violations_combine_to_most_severe_decision():
    plan = _plan([
        _step("DELETE", "/employees/1", risk_level="high"),
        _step("POST", "/absences", risk_level="medium"),
    ])
    rules = [_rule("DELETE", "/employees/*")]
    result = check_execution_policy(plan, _policy(), rules, "test")

    assert result.decision == BLOCK
    # Both the forbidden-rule reason and the (non-winning) risk reason should
    # still be surfaced, so the admin sees the full picture, not just the
    # first problem found.
    assert any("Forbidden endpoint rule" in r for r in result.reasons)
    assert any("risk score" in r for r in result.reasons)
