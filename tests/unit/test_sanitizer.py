import pytest
from app.security.sanitizer import is_sensitive_key, sanitize_payload, MASK_VALUE


class TestIsSensitiveKey:
    def test_authorization(self):
        assert is_sensitive_key("Authorization") is True

    def test_x_api_key(self):
        assert is_sensitive_key("x-api-key") is True

    def test_token(self):
        assert is_sensitive_key("access_token") is True

    def test_password(self):
        assert is_sensitive_key("password") is True

    def test_safe_key(self):
        assert is_sensitive_key("user_id") is False

    def test_safe_key_name(self):
        assert is_sensitive_key("username") is False

    def test_cookie(self):
        assert is_sensitive_key("cookie") is True


class TestSanitizePayload:
    def test_masks_token_field(self):
        result = sanitize_payload({"access_token": "abc123", "user": "john"})
        assert result["access_token"] == MASK_VALUE
        assert result["user"] == "john"

    def test_masks_authorization_header(self):
        result = sanitize_payload({"Authorization": "Bearer xyz"})
        assert result["Authorization"] == MASK_VALUE

    def test_nested_dict(self):
        result = sanitize_payload({"data": {"password": "secret"}})
        assert result["data"]["password"] == MASK_VALUE

    def test_list_of_dicts(self):
        result = sanitize_payload([{"token": "t1"}, {"user": "alice"}])
        assert result[0]["token"] == MASK_VALUE
        assert result[1]["user"] == "alice"

    def test_passthrough_non_sensitive(self):
        payload = {"id": 1, "name": "test"}
        assert sanitize_payload(payload) == payload

    def test_passthrough_string(self):
        assert sanitize_payload("hello") == "hello"

    def test_passthrough_none(self):
        assert sanitize_payload(None) is None

    def test_empty_dict(self):
        assert sanitize_payload({}) == {}
