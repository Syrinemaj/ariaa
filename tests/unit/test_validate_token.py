"""
Unit tests for validate-token logic.
Tests pure functions and Pydantic validators without starting the full app.
"""
import base64

import pytest
from pydantic import ValidationError

from app.api.automation import (
    TokenType,
    ValidateTokenRequest,
    ValidateTokenResponse,
    _build_auth_headers,
)


# ── ValidateTokenRequest validators ──────────────────────────────────────────

class TestValidateTokenRequest:
    VALID = {
        "base_url": "https://api.example.com",
        "token_type": "bearer",
        "token_value": "eyJhbGciOiJIUzI1NiJ9.payload.sig",
    }

    def test_valid_bearer_request_parses(self):
        req = ValidateTokenRequest(**self.VALID)
        assert req.token_type == TokenType.bearer
        assert req.base_url == "https://api.example.com"

    def test_empty_token_value_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            ValidateTokenRequest(**{**self.VALID, "token_value": "   "})
        assert "TOKEN_EMPTY" in str(exc_info.value)

    def test_empty_base_url_raises(self):
        with pytest.raises(ValidationError):
            ValidateTokenRequest(**{**self.VALID, "base_url": ""})

    def test_base_url_trailing_slash_stripped(self):
        req = ValidateTokenRequest(**{**self.VALID, "base_url": "https://api.example.com/"})
        assert req.base_url == "https://api.example.com"

    def test_token_value_whitespace_stripped(self):
        req = ValidateTokenRequest(**{**self.VALID, "token_value": "  mytoken  "})
        assert req.token_value == "mytoken"

    def test_invalid_token_type_raises(self):
        with pytest.raises(ValidationError):
            ValidateTokenRequest(**{**self.VALID, "token_type": "oauth2"})

    def test_default_probe_path_is_root(self):
        req = ValidateTokenRequest(**self.VALID)
        assert req.probe_path == "/"

    def test_api_key_with_custom_header(self):
        req = ValidateTokenRequest(
            base_url="https://api.example.com",
            token_type="api_key",
            token_value="sk-abc123",
            header_name="X-Custom-Key",
        )
        assert req.header_name == "X-Custom-Key"

    def test_basic_with_username(self):
        req = ValidateTokenRequest(
            base_url="https://api.example.com",
            token_type="basic",
            token_value="mypassword",
            username="admin",
        )
        assert req.username == "admin"


# ── _build_auth_headers ───────────────────────────────────────────────────────

class TestBuildAuthHeaders:
    def _make(self, token_type: str, token_value: str, **kwargs) -> ValidateTokenRequest:
        return ValidateTokenRequest(
            base_url="https://api.example.com",
            token_type=token_type,
            token_value=token_value,
            **kwargs,
        )

    def test_bearer_produces_authorization_header(self):
        req = self._make("bearer", "my-token")
        headers = _build_auth_headers(req)
        assert headers == {"Authorization": "Bearer my-token"}

    def test_api_key_default_header_name(self):
        req = self._make("api_key", "sk-abc")
        headers = _build_auth_headers(req)
        assert headers == {"X-Api-Key": "sk-abc"}

    def test_api_key_custom_header_name(self):
        req = self._make("api_key", "sk-abc", header_name="X-Token")
        headers = _build_auth_headers(req)
        assert headers == {"X-Token": "sk-abc"}

    def test_basic_produces_base64_authorization(self):
        req = self._make("basic", "secret", username="admin")
        headers = _build_auth_headers(req)
        expected = base64.b64encode(b"admin:secret").decode()
        assert headers == {"Authorization": f"Basic {expected}"}

    def test_basic_empty_username(self):
        req = self._make("basic", "secret")
        headers = _build_auth_headers(req)
        expected = base64.b64encode(b":secret").decode()
        assert headers == {"Authorization": f"Basic {expected}"}

    def test_bearer_header_name_is_authorization(self):
        req = self._make("bearer", "tok")
        headers = _build_auth_headers(req)
        assert "Authorization" in headers
        assert headers["Authorization"].startswith("Bearer ")

    def test_api_key_header_name_whitespace_stripped(self):
        req = self._make("api_key", "sk-abc", header_name="  X-Api-Key  ")
        headers = _build_auth_headers(req)
        assert "X-Api-Key" in headers


# ── ValidateTokenResponse ────────────────────────────────────────────────────

class TestValidateTokenResponse:
    def test_valid_response(self):
        resp = ValidateTokenResponse(valid=True, error_code=None, message="OK", status_code=200)
        assert resp.valid is True
        assert resp.error_code is None

    def test_expired_response(self):
        resp = ValidateTokenResponse(
            valid=False,
            error_code="TOKEN_EXPIRED",
            message="Token expired",
            status_code=401,
        )
        assert resp.valid is False
        assert resp.error_code == "TOKEN_EXPIRED"
        assert resp.status_code == 401

    def test_unreachable_response_has_no_status_code(self):
        resp = ValidateTokenResponse(
            valid=False,
            error_code="API_UNREACHABLE",
            message="Cannot reach API",
        )
        assert resp.status_code is None
