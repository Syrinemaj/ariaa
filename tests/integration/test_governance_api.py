from unittest.mock import AsyncMock, patch

from app.models.governance import DEFAULT_ENVIRONMENT_POLICIES, ForbiddenEndpointRule, GovernancePolicy


def _policy(**overrides):
    defaults = dict(
        id="policy-1",
        org_id="mock-org-id",
        risk_threshold_low=1,
        risk_threshold_high=10,
        environment_policies=dict(DEFAULT_ENVIRONMENT_POLICIES),
        updated_by=None,
        updated_at=None,
    )
    defaults.update(overrides)
    policy = GovernancePolicy()
    for k, v in defaults.items():
        setattr(policy, k, v)
    return policy


def _rule(**overrides):
    defaults = dict(
        id="rule-1", org_id="mock-org-id", method="DELETE", path_pattern="/employees/*",
        created_by="mock-admin-id", created_at=None,
    )
    defaults.update(overrides)
    rule = ForbiddenEndpointRule()
    for k, v in defaults.items():
        setattr(rule, k, v)
    return rule


class TestGetPolicy:
    def test_returns_policy(self, client):
        with patch("app.api.governance.governance_service.get_or_create_policy", new=AsyncMock(return_value=_policy())):
            response = client.get("/governance/policy")

        assert response.status_code == 200
        data = response.json()
        assert data["risk_threshold_low"] == 1
        assert data["risk_threshold_high"] == 10
        assert data["environment_policies"] == DEFAULT_ENVIRONMENT_POLICIES


class TestUpdatePolicy:
    def test_valid_update_returns_200_and_logs_audit_event(self, client):
        updated = _policy(risk_threshold_low=2, risk_threshold_high=9, updated_by="mock-admin-id")
        with (
            patch("app.api.governance.governance_service.update_policy", new=AsyncMock(return_value=updated)),
            patch("app.api.governance.log_audit_event", new=AsyncMock()) as mock_audit,
        ):
            response = client.patch("/governance/policy", json={"risk_threshold_low": 2, "risk_threshold_high": 9})

        assert response.status_code == 200
        assert response.json()["risk_threshold_low"] == 2
        mock_audit.assert_awaited_once()
        assert mock_audit.call_args.kwargs["action"] == "GOVERNANCE_POLICY_UPDATED"
        assert mock_audit.call_args.kwargs["resource_type"] == "governance_policy"

    def test_invalid_thresholds_return_400(self, client):
        with patch(
            "app.api.governance.governance_service.update_policy",
            new=AsyncMock(side_effect=ValueError("risk_threshold_low cannot be greater than risk_threshold_high")),
        ):
            response = client.patch("/governance/policy", json={"risk_threshold_low": 20, "risk_threshold_high": 5})

        assert response.status_code == 400

    def test_unknown_environment_returns_400(self, client):
        with patch(
            "app.api.governance.governance_service.update_policy",
            new=AsyncMock(side_effect=ValueError("Unknown environment(s): staging")),
        ):
            response = client.patch("/governance/policy", json={"environment_policies": {"staging": "full_access"}})

        assert response.status_code == 400


class TestForbiddenRules:
    def test_list_rules(self, client):
        with patch(
            "app.api.governance.governance_service.list_forbidden_rules",
            new=AsyncMock(return_value=[_rule()]),
        ):
            response = client.get("/governance/forbidden-rules")

        assert response.status_code == 200
        rules = response.json()["rules"]
        assert len(rules) == 1
        assert rules[0]["path_pattern"] == "/employees/*"

    def test_create_rule_returns_201_and_logs_audit_event(self, client):
        with (
            patch(
                "app.api.governance.governance_service.create_forbidden_rule",
                new=AsyncMock(return_value=_rule()),
            ),
            patch("app.api.governance.log_audit_event", new=AsyncMock()) as mock_audit,
        ):
            response = client.post(
                "/governance/forbidden-rules", json={"method": "DELETE", "path_pattern": "/employees/*"}
            )

        assert response.status_code == 201
        assert response.json()["path_pattern"] == "/employees/*"
        mock_audit.assert_awaited_once()
        assert mock_audit.call_args.kwargs["action"] == "GOVERNANCE_FORBIDDEN_RULE_CREATED"

    def test_create_rule_blank_path_returns_400(self, client):
        with patch(
            "app.api.governance.governance_service.create_forbidden_rule",
            new=AsyncMock(side_effect=ValueError("path_pattern is required")),
        ):
            response = client.post("/governance/forbidden-rules", json={"path_pattern": "   "})

        assert response.status_code == 400

    def test_delete_rule_returns_204_and_logs_audit_event(self, client):
        with (
            patch(
                "app.api.governance.governance_service.delete_forbidden_rule", new=AsyncMock(return_value=True)
            ),
            patch("app.api.governance.log_audit_event", new=AsyncMock()) as mock_audit,
        ):
            response = client.delete("/governance/forbidden-rules/rule-1")

        assert response.status_code == 204
        mock_audit.assert_awaited_once()
        assert mock_audit.call_args.kwargs["action"] == "GOVERNANCE_FORBIDDEN_RULE_DELETED"

    def test_delete_missing_rule_returns_404(self, client):
        with patch(
            "app.api.governance.governance_service.delete_forbidden_rule", new=AsyncMock(return_value=False)
        ):
            response = client.delete("/governance/forbidden-rules/does-not-exist")

        assert response.status_code == 404
