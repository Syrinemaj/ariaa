import json
from unittest.mock import AsyncMock, patch

from app.models.connection import Connection


def _connection(**overrides):
    defaults = dict(
        id="conn-1", org_id="mock-org-id", name="HR System", base_url="https://hr.example.com",
        environment="test", auth_type="api_key", encrypted_secret="gAAAAA-fernet-token-not-plaintext",
        status="active", secret_rotated_at=None, created_by="mock-admin-id", created_at=None, updated_at=None,
    )
    defaults.update(overrides)
    conn = Connection()
    for k, v in defaults.items():
        setattr(conn, k, v)
    return conn


def _assert_no_secret_leak(response_json, forbidden_value="gAAAAA-fernet-token-not-plaintext"):
    dumped = json.dumps(response_json)
    assert "encrypted_secret" not in dumped
    assert forbidden_value not in dumped


class TestListConnections:
    def test_admin_lists_connections_without_secrets(self, client):
        with patch(
            "app.api.connections.connection_service.list_connections_for_admin",
            new=AsyncMock(return_value=[_connection()]),
        ):
            response = client.get("/connections")

        assert response.status_code == 200
        data = response.json()
        _assert_no_secret_leak(data)
        assert data["connections"][0]["name"] == "HR System"


class TestCreateConnection:
    def test_create_returns_201_without_secret_and_logs_audit(self, client):
        with (
            patch(
                "app.api.connections.connection_service.create_connection",
                new=AsyncMock(return_value=_connection()),
            ),
            patch("app.api.connections.log_audit_event", new=AsyncMock()) as mock_audit,
        ):
            response = client.post(
                "/connections",
                json={
                    "name": "HR System", "base_url": "https://hr.example.com",
                    "environment": "test", "auth_type": "api_key", "secret": "super-secret-value",
                },
            )

        assert response.status_code == 201
        data = response.json()
        _assert_no_secret_leak(data)
        assert "super-secret-value" not in json.dumps(data)
        mock_audit.assert_awaited_once()
        assert mock_audit.call_args.kwargs["action"] == "CONNECTION_CREATED"
        # The secret itself must never reach audit metadata either.
        assert "super-secret-value" not in json.dumps(mock_audit.call_args.kwargs["metadata"])

    def test_create_invalid_returns_400(self, client):
        with patch(
            "app.api.connections.connection_service.create_connection",
            new=AsyncMock(side_effect=ValueError("environment must be one of ['preprod', 'prod', 'test']")),
        ):
            response = client.post(
                "/connections",
                json={
                    "name": "X", "base_url": "https://x.example.com",
                    "environment": "staging", "auth_type": "api_key", "secret": "x",
                },
            )
        assert response.status_code == 400


class TestGetConnection:
    def test_returns_connection_with_operator_ids(self, client):
        with (
            patch(
                "app.api.connections.connection_service.get_connection",
                new=AsyncMock(return_value=_connection()),
            ),
            patch(
                "app.api.connections.connection_service.list_operator_ids",
                new=AsyncMock(return_value=["op-1", "op-2"]),
            ),
        ):
            response = client.get("/connections/conn-1")

        assert response.status_code == 200
        data = response.json()
        _assert_no_secret_leak(data)
        assert data["operator_ids"] == ["op-1", "op-2"]

    def test_returns_404_when_missing(self, client):
        with patch(
            "app.api.connections.connection_service.get_connection", new=AsyncMock(return_value=None)
        ):
            response = client.get("/connections/does-not-exist")
        assert response.status_code == 404


class TestUpdateConnection:
    def test_update_returns_200(self, client):
        with (
            patch(
                "app.api.connections.connection_service.update_connection",
                new=AsyncMock(return_value=_connection(base_url="https://new.example.com")),
            ),
            patch(
                "app.api.connections.connection_service.list_operator_ids", new=AsyncMock(return_value=[])
            ),
            patch("app.api.connections.log_audit_event", new=AsyncMock()) as mock_audit,
        ):
            response = client.patch("/connections/conn-1", json={"base_url": "https://new.example.com"})

        assert response.status_code == 200
        data = response.json()
        _assert_no_secret_leak(data)
        assert data["base_url"] == "https://new.example.com"
        assert mock_audit.call_args.kwargs["action"] == "CONNECTION_UPDATED"

    def test_update_missing_returns_404(self, client):
        with patch(
            "app.api.connections.connection_service.update_connection", new=AsyncMock(return_value=None)
        ):
            response = client.patch("/connections/does-not-exist", json={"name": "x"})
        assert response.status_code == 404

    def test_update_invalid_returns_400(self, client):
        with patch(
            "app.api.connections.connection_service.update_connection",
            new=AsyncMock(side_effect=ValueError("A connection with this name already exists")),
        ):
            response = client.patch("/connections/conn-1", json={"name": "dup"})
        assert response.status_code == 400


class TestRotateSecret:
    def test_rotate_returns_200_without_secret(self, client):
        with (
            patch(
                "app.api.connections.connection_service.rotate_secret",
                new=AsyncMock(return_value=_connection()),
            ),
            patch("app.api.connections.log_audit_event", new=AsyncMock()) as mock_audit,
        ):
            response = client.post("/connections/conn-1/rotate-secret", json={"secret": "brand-new-secret"})

        assert response.status_code == 200
        data = response.json()
        _assert_no_secret_leak(data)
        assert "brand-new-secret" not in json.dumps(data)
        assert "brand-new-secret" not in json.dumps(mock_audit.call_args.kwargs["metadata"])

    def test_rotate_missing_returns_404(self, client):
        with patch(
            "app.api.connections.connection_service.rotate_secret", new=AsyncMock(return_value=None)
        ):
            response = client.post("/connections/does-not-exist/rotate-secret", json={"secret": "x"})
        assert response.status_code == 404


class TestRevokeReactivate:
    def test_revoke_returns_200(self, client):
        with (
            patch(
                "app.api.connections.connection_service.revoke_connection",
                new=AsyncMock(return_value=_connection(status="revoked")),
            ),
            patch("app.api.connections.log_audit_event", new=AsyncMock()),
        ):
            response = client.post("/connections/conn-1/revoke")
        assert response.status_code == 200
        assert response.json()["status"] == "revoked"

    def test_revoke_missing_returns_404(self, client):
        with patch(
            "app.api.connections.connection_service.revoke_connection", new=AsyncMock(return_value=None)
        ):
            response = client.post("/connections/does-not-exist/revoke")
        assert response.status_code == 404

    def test_reactivate_returns_200(self, client):
        with (
            patch(
                "app.api.connections.connection_service.reactivate_connection",
                new=AsyncMock(return_value=_connection(status="active")),
            ),
            patch("app.api.connections.log_audit_event", new=AsyncMock()),
        ):
            response = client.post("/connections/conn-1/reactivate")
        assert response.status_code == 200
        assert response.json()["status"] == "active"


class TestConnectionTest:
    def test_test_route_returns_probe_result(self, client):
        with (
            patch(
                "app.api.connections.connection_service.get_connection",
                new=AsyncMock(return_value=_connection()),
            ),
            patch(
                "app.api.connections.connection_service.test_connection",
                new=AsyncMock(return_value={"success": True, "status_code": 200, "message": "Connection reachable."}),
            ),
            patch("app.api.connections.log_audit_event", new=AsyncMock()) as mock_audit,
        ):
            response = client.post("/connections/conn-1/test")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        _assert_no_secret_leak(data)
        assert mock_audit.call_args.kwargs["action"] == "CONNECTION_TESTED"

    def test_test_route_missing_connection_returns_404(self, client):
        with patch(
            "app.api.connections.connection_service.get_connection", new=AsyncMock(return_value=None)
        ):
            response = client.post("/connections/does-not-exist/test")
        assert response.status_code == 404


class TestOperatorAssignment:
    def test_assign_returns_201(self, client):
        with (
            patch("app.api.connections.connection_service.assign_operator", new=AsyncMock(return_value=None)),
            patch("app.api.connections.log_audit_event", new=AsyncMock()) as mock_audit,
        ):
            response = client.post("/connections/conn-1/operators", json={"user_id": "op-1"})

        assert response.status_code == 201
        assert mock_audit.call_args.kwargs["action"] == "CONNECTION_OPERATOR_ASSIGNED"

    def test_assign_duplicate_returns_409(self, client):
        with patch(
            "app.api.connections.connection_service.assign_operator",
            new=AsyncMock(side_effect=ValueError("User is already assigned to this connection")),
        ):
            response = client.post("/connections/conn-1/operators", json={"user_id": "op-1"})
        assert response.status_code == 409

    def test_assign_unknown_user_returns_404(self, client):
        with patch(
            "app.api.connections.connection_service.assign_operator",
            new=AsyncMock(side_effect=ValueError("User not found")),
        ):
            response = client.post("/connections/conn-1/operators", json={"user_id": "does-not-exist"})
        assert response.status_code == 404

    def test_unassign_returns_204(self, client):
        with (
            patch(
                "app.api.connections.connection_service.unassign_operator", new=AsyncMock(return_value=True)
            ),
            patch("app.api.connections.log_audit_event", new=AsyncMock()) as mock_audit,
        ):
            response = client.delete("/connections/conn-1/operators/op-1")
        assert response.status_code == 204
        assert mock_audit.call_args.kwargs["action"] == "CONNECTION_OPERATOR_UNASSIGNED"

    def test_unassign_missing_returns_404(self, client):
        with patch(
            "app.api.connections.connection_service.unassign_operator", new=AsyncMock(return_value=False)
        ):
            response = client.delete("/connections/conn-1/operators/op-1")
        assert response.status_code == 404
