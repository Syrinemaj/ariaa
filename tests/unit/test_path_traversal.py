"""Tests for Fix 3.2 — Path Traversal + URL injection security."""
import pytest

from app.automation.executor import (
    PathTraversalError,
    _build_and_validate_url,
    _contains_traversal,
    _resolve_path_params,
)


class TestContainsTraversal:
    def test_dotdot_detected(self):
        assert _contains_traversal("../../admin") is True

    def test_double_slash_detected(self):
        assert _contains_traversal("//evil.com") is True

    def test_encoded_dotdot_detected(self):
        assert _contains_traversal("%2e%2e/secret") is True

    def test_encoded_slash_detected(self):
        assert _contains_traversal("%2f%2fsomething") is True

    def test_double_encoded_dot_detected(self):
        assert _contains_traversal("%252e%252e") is True

    def test_valid_id_passes(self):
        assert _contains_traversal("valid-id-123") is False

    def test_email_like_passes(self):
        assert _contains_traversal("user@domain.com") is False

    def test_uuid_passes(self):
        assert _contains_traversal("550e8400-e29b-41d4-a716-446655440000") is False


class TestResolvePathParams:
    def test_simple_substitution(self):
        result = _resolve_path_params("/users/{id}", {"id": "123"}, {})
        assert result == "/users/123"

    def test_url_encoding_applied(self):
        # Spaces and special chars must be encoded
        result = _resolve_path_params("/items/{name}", {"name": "hello world"}, {})
        assert " " not in result
        assert "%20" in result or "+" in result

    def test_slash_in_value_encoded(self):
        # A slash in a param value must be encoded — not injected as path separator
        result = _resolve_path_params("/files/{name}", {"name": "file/name"}, {})
        assert "/files/file/name" not in result  # raw slash must not appear
        assert "%2F" in result or "%2f" in result

    def test_traversal_in_param_raises(self):
        with pytest.raises(PathTraversalError, match="traversal"):
            _resolve_path_params("/users/{id}", {"id": "../../admin"}, {})

    def test_encoded_traversal_raises(self):
        with pytest.raises(PathTraversalError, match="traversal"):
            _resolve_path_params("/users/{id}", {"id": "%2e%2e/secret"}, {})

    def test_state_values_substituted(self):
        result = _resolve_path_params(
            "/orders/{order_id}",
            {},
            {"order_id": "ORD-999"},
        )
        assert result == "/orders/ORD-999"

    def test_payload_overrides_state(self):
        # payload takes precedence over state for same key
        result = _resolve_path_params(
            "/orders/{id}",
            {"id": "payload-id"},
            {"id": "state-id"},
        )
        assert "payload-id" in result


class TestBuildAndValidateUrl:
    def test_normal_url_built(self):
        url = _build_and_validate_url("https://api.example.com", "/v1/users/123")
        assert url == "https://api.example.com/v1/users/123"

    def test_no_base_returns_path(self):
        url = _build_and_validate_url(None, "/v1/users/123")
        assert url == "/v1/users/123"

    def test_host_change_raises(self):
        # Param injection that tries to change the netloc
        with pytest.raises(PathTraversalError, match="host changed"):
            _build_and_validate_url(
                "https://api.example.com",
                # After urljoin, //evil.com would take over the netloc
                "//evil.com/admin",
            )
