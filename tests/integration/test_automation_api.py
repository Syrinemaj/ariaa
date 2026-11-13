from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.automation.models import AutomationExecutionResult, StepExecutionResult
from app.models.governance import DEFAULT_ENVIRONMENT_POLICIES
from app.planner.models import AutomationPlan, BusinessIntent, PlanStep


def _mock_connection(environment="test", auth_type="api_key", status="active"):
    conn = MagicMock()
    conn.id = "conn-mock-1"
    conn.base_url = "https://api.example.com"
    conn.environment = environment
    conn.auth_type = auth_type
    conn.status = status
    return conn


def _mock_policy(low=1, high=10):
    policy = MagicMock()
    policy.risk_threshold_low = low
    policy.risk_threshold_high = high
    policy.environment_policies = dict(DEFAULT_ENVIRONMENT_POLICIES)
    return policy


@contextmanager
def patched_connection_and_governance(connection=None, forbidden_rules=None):
    """/automation/execute now resolves a Connection (instead of trusting a
    client-supplied base_url/auth_headers) and runs it through the
    governance policy engine on every non-dry-run call — every test below
    needs these mocked regardless of what it's actually asserting about."""
    with (
        patch(
            "app.api.automation.connection_service.get_connection",
            new=AsyncMock(return_value=connection or _mock_connection()),
        ),
        patch(
            "app.api.automation.connection_service.user_can_use_connection", new=AsyncMock(return_value=True)
        ),
        patch(
            "app.api.automation.connection_service.get_decrypted_secret_for_execution",
            return_value="mock-decrypted-secret",
        ),
        patch("app.api.automation.connection_service.build_auth_headers", return_value={}),
        patch(
            "app.api.automation.governance_service.get_or_create_policy",
            new=AsyncMock(return_value=_mock_policy()),
        ),
        patch(
            "app.api.automation.governance_service.list_forbidden_rules",
            new=AsyncMock(return_value=forbidden_rules or []),
        ),
        # Pre-existing gaps in this mocked-db test setup, unrelated to
        # connections/governance: resolve_single_team_id(db, ...) and
        # log_audit_event(db=db, ...) are both awaited directly against the
        # route's `db`, which the global `client` fixture's get_db override
        # sets to a plain (non-async) MagicMock — any real await on it
        # raises "object MagicMock can't be used in 'await' expression",
        # regardless of whether execute_automation itself is mocked.
        patch("app.api.automation.resolve_single_team_id", new=AsyncMock(return_value=None)),
        patch("app.api.automation.log_audit_event", new=AsyncMock()),
    ):
        yield


def make_plan_payload(requires_approval=True, method="GET"):
    return {
        "run_id": "run-test-123",
        "instruction": "list all users",
        "intent": {
            "instruction": "list all users",
            "intent": "list",
            "action": "list",
            "confidence": 0.95,
        },
        "workflow_name": "user-listing",
        "steps": [
            {
                "order": 1,
                "endpoint_id": "ep-1",
                "method": method,
                "path": "/api/users",
                "canonical_key": f"{method} /api/users",
                "risk_level": "low",
            }
        ],
        "requires_approval": requires_approval,
        "dry_run_default": True,
    }


def make_execution_result(dry_run=True, status="completed"):
    return AutomationExecutionResult(
        status=status,
        dry_run=dry_run,
        success_count=1,
        failed_count=0,
        total_steps=1,
        results=[
            StepExecutionResult(
                step_order=1,
                method="GET",
                path="/api/users",
                status="success",
                status_code=200 if not dry_run else None,
                request_payload={},
                response_payload={"users": []},
            )
        ],
        metadata={"duration_seconds": 0.1},
    )


def _mock_http_response(status_code: int) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    return resp


class TestValidateToken:
    @pytest.fixture(autouse=True)
    def _reset_rate_limiter(self):
        # /automation/validate-token is rate-limited (app/core/rate_limit.py,
        # settings.RATE_LIMIT_AUTH, shared Redis-backed counter keyed on the
        # caller — "testclient" for every call made through TestClient). This
        # class has more test methods than the limit allows, so without a
        # reset the N+1-th test in a run gets a 429 instead of exercising its
        # own scenario — not a bug in the route, just missing test isolation
        # from a limiter that's deliberately shared across workers in
        # production. Reset before each test rather than after, so a failed
        # test doesn't leave the counter dirty for the next one.
        from app.core.rate_limit import limiter
        limiter.reset()
        yield

    BASE_PAYLOAD = {
        "base_url": "https://api.example.com",
        "token_type": "bearer",
        "token_value": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyIn0.sig",
        "probe_path": "/health",
    }

    def _post(self, client, payload: dict):
        return client.post("/automation/validate-token", json=payload)

    # ── input validation ──────────────────────────────────────────────────────

    def test_empty_token_returns_422(self, client):
        payload = {**self.BASE_PAYLOAD, "token_value": "   "}
        response = self._post(client, payload)
        assert response.status_code == 422

    def test_empty_base_url_returns_422(self, client):
        payload = {**self.BASE_PAYLOAD, "base_url": ""}
        response = self._post(client, payload)
        assert response.status_code == 422

    def test_malformed_bearer_token_returns_token_malformed(self, client):
        # Two-segment string looks like a broken JWT
        payload = {**self.BASE_PAYLOAD, "token_value": "header.payload"}
        with patch("app.api.automation.create_safe_client"):
            response = self._post(client, payload)
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert data["error_code"] == "TOKEN_MALFORMED"

    # ── HTTP status mapping ───────────────────────────────────────────────────

    def test_200_from_target_returns_valid_true(self, client):
        mock_resp = _mock_http_response(200)
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=AsyncMock(get=AsyncMock(return_value=mock_resp)))
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.api.automation.create_safe_client", return_value=mock_cm):
            response = self._post(client, self.BASE_PAYLOAD)

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["error_code"] is None
        assert data["status_code"] == 200

    def test_401_from_target_returns_token_expired(self, client):
        mock_resp = _mock_http_response(401)
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=AsyncMock(get=AsyncMock(return_value=mock_resp)))
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.api.automation.create_safe_client", return_value=mock_cm):
            response = self._post(client, self.BASE_PAYLOAD)

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert data["error_code"] == "TOKEN_EXPIRED"
        assert data["status_code"] == 401

    def test_403_from_target_returns_token_invalid(self, client):
        mock_resp = _mock_http_response(403)
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=AsyncMock(get=AsyncMock(return_value=mock_resp)))
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.api.automation.create_safe_client", return_value=mock_cm):
            response = self._post(client, self.BASE_PAYLOAD)

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert data["error_code"] == "TOKEN_INVALID"
        assert data["status_code"] == 403

    def test_500_from_target_returns_unknown_error(self, client):
        mock_resp = _mock_http_response(500)
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=AsyncMock(get=AsyncMock(return_value=mock_resp)))
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.api.automation.create_safe_client", return_value=mock_cm):
            response = self._post(client, self.BASE_PAYLOAD)

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert data["error_code"] == "UNKNOWN_ERROR"

    # ── network errors ────────────────────────────────────────────────────────

    def test_connect_error_returns_api_unreachable(self, client):
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(
            return_value=AsyncMock(get=AsyncMock(side_effect=httpx.ConnectError("refused")))
        )
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.api.automation.create_safe_client", return_value=mock_cm):
            response = self._post(client, self.BASE_PAYLOAD)

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert data["error_code"] == "API_UNREACHABLE"

    def test_timeout_returns_api_unreachable(self, client):
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(
            return_value=AsyncMock(get=AsyncMock(side_effect=httpx.ConnectTimeout("timed out")))
        )
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.api.automation.create_safe_client", return_value=mock_cm):
            response = self._post(client, self.BASE_PAYLOAD)

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert data["error_code"] == "API_UNREACHABLE"

    # ── token types ───────────────────────────────────────────────────────────

    def test_api_key_type_accepted(self, client):
        mock_resp = _mock_http_response(200)
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=AsyncMock(get=AsyncMock(return_value=mock_resp)))
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        payload = {
            "base_url": "https://api.example.com",
            "token_type": "api_key",
            "token_value": "sk-abc123",
            "header_name": "X-Api-Key",
            "probe_path": "/health",
        }
        with patch("app.api.automation.create_safe_client", return_value=mock_cm):
            response = self._post(client, payload)

        assert response.status_code == 200
        assert response.json()["valid"] is True

    def test_basic_auth_type_accepted(self, client):
        mock_resp = _mock_http_response(200)
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=AsyncMock(get=AsyncMock(return_value=mock_resp)))
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        payload = {
            "base_url": "https://api.example.com",
            "token_type": "basic",
            "token_value": "mypassword",
            "username": "admin",
            "probe_path": "/health",
        }
        with patch("app.api.automation.create_safe_client", return_value=mock_cm):
            response = self._post(client, payload)

        assert response.status_code == 200
        assert response.json()["valid"] is True

    def test_ssrf_blocked_url_returns_400(self, client):
        from app.security.pinned_dns_transport import SSRFError

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(side_effect=SSRFError("blocked"))
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.api.automation.create_safe_client", return_value=mock_cm):
            response = self._post(client, self.BASE_PAYLOAD)

        assert response.status_code == 400


class TestCreatePlan:
    def test_returns_404_for_unknown_run(self, client):
        with patch("app.api.automation.get_run_by_id", return_value=None):
            response = client.post(
                "/automation/plan",
                json={"run_id": "nonexistent", "instruction": "do something"},
            )
        assert response.status_code == 404

    def test_creates_plan_for_valid_run(self, client):
        from app.db.session import get_db
        from app.main import app

        # This path logs an audit event, which does `await db.flush()` — not
        # awaitable on the plain MagicMock the global `client` fixture
        # normally injects (same workaround already used by
        # TestExecutePlan.test_governance_block_returns_403_before_execute_automation_is_called
        # above, for the same reason).
        mock_db = MagicMock()
        mock_db.flush = AsyncMock()
        original_get_db = app.dependency_overrides.get(get_db)
        app.dependency_overrides[get_db] = lambda: (yield mock_db)

        mock_run = MagicMock()
        mock_plan = AutomationPlan(
            run_id="run-123",
            instruction="list users",
            intent=BusinessIntent(
                instruction="list users",
                intent="list",
                action="list",
                confidence=0.9,
            ),
            workflow_name="user-flow",
            # A plan with no steps is correctly rejected with 400
            # NO_MATCHING_ENDPOINTS by the route (app/api/automation.py) —
            # this test exercises the success path, so it needs at least
            # one real step, not an empty list.
            steps=[
                PlanStep(
                    order=1,
                    endpoint_id="endpoint-1",
                    method="GET",
                    path="/users",
                    canonical_key="GET /users",
                ),
            ],
        )
        mock_validation = MagicMock()
        mock_validation.is_valid = True
        mock_validation.issues = []
        mock_validation.model_dump.return_value = {"is_valid": True, "issues": []}

        try:
            with patch("app.api.automation.get_run_by_id", return_value=mock_run), \
                 patch("app.api.automation.create_plan_from_instruction",
                       return_value=(mock_plan, mock_validation)):
                response = client.post(
                    "/automation/plan",
                    json={"run_id": "run-123", "instruction": "list users"},
                )
        finally:
            if original_get_db is not None:
                app.dependency_overrides[get_db] = original_get_db

        assert response.status_code == 200
        data = response.json()
        assert "plan" in data
        assert "validation" in data


class TestExecutePlan:
    def test_dry_run_succeeds(self, client):
        mock_run = MagicMock()
        mock_run.id = "automation-run-1"
        mock_result = make_execution_result(dry_run=True)

        with patched_connection_and_governance(), patch(
            "app.api.automation.execute_automation",
            new_callable=AsyncMock,
            return_value=(mock_run, mock_result),
        ):
            response = client.post(
                "/automation/execute",
                json={
                    "plan": make_plan_payload(requires_approval=True),
                    "connection_id": "conn-mock-1",
                    "dry_run": True,
                    "approval_granted": False,
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["dry_run"] is True
        assert data["status"] == "completed"
        assert data["success_count"] == 1

    def test_real_execution_without_approval_returns_403(self, client):
        from app.security.execution_guard import ExecutionGuardError

        with patched_connection_and_governance(), patch(
            "app.api.automation.execute_automation",
            new_callable=AsyncMock,
            side_effect=ExecutionGuardError("Real execution requires explicit approval."),
        ):
            response = client.post(
                "/automation/execute",
                json={
                    "plan": make_plan_payload(requires_approval=True),
                    "connection_id": "conn-mock-1",
                    "dry_run": False,
                    "approval_granted": False,
                },
            )

        assert response.status_code == 403
        assert "approval" in response.json()["detail"].lower()

    def test_delete_without_allow_returns_403(self, client):
        from app.security.execution_guard import ExecutionGuardError

        with patched_connection_and_governance(), patch(
            "app.api.automation.execute_automation",
            new_callable=AsyncMock,
            side_effect=ExecutionGuardError("Method DELETE is forbidden by default."),
        ):
            response = client.post(
                "/automation/execute",
                json={
                    "plan": make_plan_payload(requires_approval=False, method="DELETE"),
                    "connection_id": "conn-mock-1",
                    "dry_run": False,
                    "approval_granted": True,
                },
            )

        assert response.status_code == 403

    def test_missing_connection_returns_404(self, client):
        with patch(
            "app.api.automation.connection_service.get_connection", new=AsyncMock(return_value=None)
        ):
            response = client.post(
                "/automation/execute",
                json={
                    "plan": make_plan_payload(),
                    "connection_id": "does-not-exist",
                    "dry_run": True,
                },
            )
        assert response.status_code == 404

    def test_unassigned_connection_returns_403(self, client):
        with (
            patch(
                "app.api.automation.connection_service.get_connection",
                new=AsyncMock(return_value=_mock_connection()),
            ),
            patch(
                "app.api.automation.connection_service.user_can_use_connection",
                new=AsyncMock(return_value=False),
            ),
        ):
            response = client.post(
                "/automation/execute",
                json={
                    "plan": make_plan_payload(),
                    "connection_id": "conn-mock-1",
                    "dry_run": True,
                },
            )
        assert response.status_code == 403

    def test_operator_allow_decision_skips_approval_flow(self, client):
        """Core Feature 1 behavior: an OPERATOR whose plan governance rates
        ALLOW (low risk, full_access environment) executes directly — no
        pending-approval round trip, unlike the pre-governance behavior
        where ANY non-dry-run operator call always required approval."""
        from app.auth.dependencies import get_current_user, require_admin_or_operator
        from app.main import app
        from app.models.user import UserRole

        mock_operator = MagicMock()
        mock_operator.id = "mock-operator-id"
        mock_operator.org_id = "mock-org-id"
        mock_operator.role = UserRole.OPERATOR

        mock_run = MagicMock()
        mock_run.id = "automation-run-2"
        mock_result = make_execution_result(dry_run=False, status="completed")

        original_get_current_user = app.dependency_overrides.get(get_current_user)
        original_require_admin_or_operator = app.dependency_overrides.get(require_admin_or_operator)
        app.dependency_overrides[get_current_user] = lambda: mock_operator
        app.dependency_overrides[require_admin_or_operator] = lambda: mock_operator
        try:
            with patched_connection_and_governance(), patch(
                "app.api.automation.execute_automation",
                new_callable=AsyncMock,
                return_value=(mock_run, mock_result),
            ) as mock_execute:
                response = client.post(
                    "/automation/execute",
                    json={
                        "plan": make_plan_payload(requires_approval=False),
                        "connection_id": "conn-mock-1",
                        "dry_run": False,
                        "approval_granted": False,
                    },
                )
        finally:
            if original_get_current_user is not None:
                app.dependency_overrides[get_current_user] = original_get_current_user
            if original_require_admin_or_operator is not None:
                app.dependency_overrides[require_admin_or_operator] = original_require_admin_or_operator

        assert response.status_code == 200, response.json()
        # approval_granted was forced True by the ALLOW decision, not by
        # the (false) client-sent value.
        assert mock_execute.call_args.kwargs["approval_granted"] is True

    def test_governance_block_returns_403_before_execute_automation_is_called(self, client):
        from app.db.session import get_db
        from app.main import app

        # A BLOCK commits the audit-log write before raising (get_db() rolls
        # back on any exception, which would otherwise silently drop it —
        # see the comment at that call site) — needs db.commit() to be
        # awaitable, unlike the plain MagicMock the global `client` fixture
        # normally injects.
        mock_db = MagicMock()
        mock_db.commit = AsyncMock()
        original_get_db = app.dependency_overrides.get(get_db)
        app.dependency_overrides[get_db] = lambda: (yield mock_db)

        forbidden_rule = MagicMock(method="GET", path_pattern="/api/users")
        try:
            with patched_connection_and_governance(forbidden_rules=[forbidden_rule]), patch(
                "app.api.automation.execute_automation", new_callable=AsyncMock
            ) as mock_execute:
                response = client.post(
                    "/automation/execute",
                    json={
                        "plan": make_plan_payload(),
                        "connection_id": "conn-mock-1",
                        "dry_run": False,
                        "approval_granted": True,
                    },
                )
        finally:
            if original_get_db is not None:
                app.dependency_overrides[get_db] = original_get_db

        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "GOVERNANCE_BLOCKED"
        mock_execute.assert_not_awaited()
        mock_db.commit.assert_awaited()
