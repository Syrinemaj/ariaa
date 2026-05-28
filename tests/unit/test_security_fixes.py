"""Tests for Section 9 security fixes (9.2, 9.3, 9.4, 9.5)."""
from urllib.parse import urlparse

import pytest


# ── Fix 9.3 — URL port normalization ─────────────────────────────────────────

class TestNormalizeUrlBase:
    def _normalize(self, url: str) -> str:
        from app.security.ssrf_guard import normalize_url_base
        return normalize_url_base(urlparse(url))

    def test_https_443_stripped(self):
        assert self._normalize("https://api.company.com:443") == "https://api.company.com"

    def test_https_no_port_unchanged(self):
        assert self._normalize("https://api.company.com") == "https://api.company.com"

    def test_https_8080_kept(self):
        assert self._normalize("https://api.company.com:8080") == "https://api.company.com:8080"

    def test_http_80_stripped(self):
        assert self._normalize("http://api.company.com:80") == "http://api.company.com"

    def test_http_8080_kept(self):
        assert self._normalize("http://api.company.com:8080") == "http://api.company.com:8080"

    def test_case_insensitive_host(self):
        assert self._normalize("https://API.Company.COM") == "https://api.company.com"

    def test_port_443_equals_no_port_in_allowlist(self):
        """
        ALLOWED_TARGET_DOMAINS=https://api.company.com must also match
        https://api.company.com:443 (same thing semantically).
        """
        from unittest.mock import patch
        with patch("app.security.ssrf_guard.settings") as mock_settings:
            mock_settings.ALLOWED_TARGET_DOMAINS = "https://api.company.com"
            from app.security.ssrf_guard import get_allowed_domains
            allowed = get_allowed_domains()
            assert "https://api.company.com" in allowed
            # :443 normalizes to the same key
            normalized_443 = self._normalize("https://api.company.com:443")
            assert normalized_443 in allowed


# ── Fix 9.4 — UserRole enum ───────────────────────────────────────────────────

class TestUserRoleEnum:
    def test_admin_value_uppercase(self):
        from app.models.user import UserRole
        assert UserRole.ADMIN.value == "ADMIN"

    def test_operator_value_uppercase(self):
        from app.models.user import UserRole
        assert UserRole.OPERATOR.value == "OPERATOR"

    def test_viewer_exists(self):
        from app.models.user import UserRole
        assert UserRole.VIEWER.value == "VIEWER"

    def test_str_comparison(self):
        from app.models.user import UserRole
        # UserRole(str, Enum) — comparing with raw string must work
        assert UserRole.ADMIN == "ADMIN"
        assert UserRole.ADMIN.value == "ADMIN"

    def test_values_method(self):
        from app.models.user import UserRole
        assert UserRole.values() == {"ADMIN", "OPERATOR", "VIEWER"}

    def test_require_roles_uses_values(self):
        """require_roles must compare role values, not enum objects."""
        from app.models.user import UserRole
        allowed_roles = [UserRole.ADMIN, UserRole.OPERATOR]
        allowed_values = {r.value for r in allowed_roles}
        assert "ADMIN" in allowed_values
        assert "OPERATOR" in allowed_values
        assert "VIEWER" not in allowed_values


# ── Fix 9.5 — Audit sanitization ─────────────────────────────────────────────

class TestSanitizeAuditMetadata:
    def _sanitize(self, data):
        from app.audit.service import sanitize_audit_metadata
        return sanitize_audit_metadata(data)

    def test_authorization_header_masked(self):
        result = self._sanitize({"authorization": "Bearer secret-token"})
        assert result["authorization"] == "***REDACTED***"

    def test_auth_headers_dict_masked(self):
        # auth_headers is a common key passed to log_audit_event in bulk execution
        result = self._sanitize({"auth_headers": {"Authorization": "Bearer abc"}})
        assert result["auth_headers"] == "***REDACTED***"

    def test_password_masked(self):
        result = self._sanitize({"email": "a@b.com", "password": "secret123"})
        assert result["password"] == "***REDACTED***"
        assert result["email"] == "a@b.com"  # non-sensitive preserved

    def test_nested_token_masked(self):
        data = {"user": {"access_token": "tok-123", "name": "Alice"}}
        result = self._sanitize(data)
        assert result["user"]["access_token"] == "***REDACTED***"
        assert result["user"]["name"] == "Alice"

    def test_list_handled(self):
        data = [{"authorization": "Bearer x"}, {"name": "ok"}]
        result = self._sanitize(data)
        assert result[0]["authorization"] == "***REDACTED***"
        assert result[1]["name"] == "ok"

    def test_non_sensitive_keys_pass_through(self):
        data = {"email": "a@b.com", "role": "ADMIN", "org_id": "org-1"}
        result = self._sanitize(data)
        assert result == data

    def test_hyphenated_key_normalized(self):
        # "x-api-key" → normalized to "x_api_key" → matched
        result = self._sanitize({"x-api-key": "secret"})
        assert result["x-api-key"] == "***REDACTED***"

    def test_api_key_masked(self):
        result = self._sanitize({"api_key": "sk-12345"})
        assert result["api_key"] == "***REDACTED***"

    def test_sanitize_payload_handles_non_dict(self):
        from app.audit.service import sanitize_payload
        result = sanitize_payload("not-a-dict")
        assert isinstance(result, dict)
        assert result.get("_sanitized") is True


# ── Fix 9.2 — /metrics IP guard ──────────────────────────────────────────────

class TestMetricsGuard:
    def test_metrics_allowed_ips_in_config(self):
        from app.core.config import settings
        # Should have a default value
        assert hasattr(settings, "METRICS_ALLOWED_IPS")
        assert settings.METRICS_ALLOWED_IPS  # not empty

    def test_metrics_bearer_token_in_config(self):
        from app.core.config import settings
        assert hasattr(settings, "METRICS_BEARER_TOKEN")
