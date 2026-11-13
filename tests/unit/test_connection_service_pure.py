from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.connections.service import build_auth_headers
from app.connections.service import test_connection as probe_connection
from app.security.ssrf_guard import SSRFError


class TestBuildAuthHeaders:
    def test_api_key_uses_x_api_key_header(self):
        assert build_auth_headers("api_key", "secret-123") == {"X-API-Key": "secret-123"}

    def test_service_account_uses_bearer(self):
        assert build_auth_headers("service_account", "secret-123") == {"Authorization": "Bearer secret-123"}

    def test_oauth_client_credentials_uses_bearer(self):
        assert build_auth_headers("oauth_client_credentials", "secret-123") == {
            "Authorization": "Bearer secret-123"
        }

    def test_unknown_auth_type_returns_empty(self):
        assert build_auth_headers("something_else", "secret-123") == {}


def _fake_connection(auth_type="api_key"):
    conn = MagicMock()
    conn.base_url = "https://target.example.com"
    conn.auth_type = auth_type
    conn.encrypted_secret = "irrelevant-for-this-mock"
    return conn


def _client_cm(response=None, raise_exc=None):
    @asynccontextmanager
    async def _create_safe_client(**kwargs):
        client = AsyncMock()
        if raise_exc:
            client.get.side_effect = raise_exc
        else:
            client.get.return_value = response
        yield client

    return _create_safe_client


class TestTestConnection:
    @pytest.mark.asyncio
    async def test_success_response(self):
        response = MagicMock(status_code=200)
        with (
            patch("app.connections.service.decrypt_secret", return_value="plain-secret"),
            patch("app.connections.service.create_safe_client", _client_cm(response=response)),
        ):
            result = await probe_connection(_fake_connection())

        assert result["success"] is True
        assert result["status_code"] == 200
        assert "plain-secret" not in str(result)

    @pytest.mark.asyncio
    async def test_401_reported_as_unauthorized(self):
        response = MagicMock(status_code=401)
        with (
            patch("app.connections.service.decrypt_secret", return_value="plain-secret"),
            patch("app.connections.service.create_safe_client", _client_cm(response=response)),
        ):
            result = await probe_connection(_fake_connection())

        assert result["success"] is False
        assert result["status_code"] == 401
        assert "plain-secret" not in str(result)

    @pytest.mark.asyncio
    async def test_connect_timeout_reported_without_raising(self):
        with (
            patch("app.connections.service.decrypt_secret", return_value="plain-secret"),
            patch(
                "app.connections.service.create_safe_client",
                _client_cm(raise_exc=httpx.ConnectTimeout("timed out")),
            ),
        ):
            result = await probe_connection(_fake_connection())

        assert result["success"] is False
        assert result["status_code"] is None

    @pytest.mark.asyncio
    async def test_ssrf_blocked_reported_without_raising(self):
        with (
            patch("app.connections.service.decrypt_secret", return_value="plain-secret"),
            patch(
                "app.connections.service.create_safe_client",
                _client_cm(raise_exc=SSRFError("blocked")),
            ),
        ):
            result = await probe_connection(_fake_connection())

        assert result["success"] is False
        assert "blocked" in result["message"]
