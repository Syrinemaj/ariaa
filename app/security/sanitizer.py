from typing import Any


SENSITIVE_KEYS = {
    "authorization", "cookie", "set-cookie", "password", "passwd", "pwd",
    "token", "access_token", "refresh_token", "id_token",
    "api_key", "apikey", "x-api-key", "secret", "client_secret",
}

MASK_VALUE = "***MASKED***"


def is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(sensitive in normalized for sensitive in SENSITIVE_KEYS)


def sanitize_dict(data: dict) -> dict:
    sanitized = {}
    for key, value in data.items():
        if is_sensitive_key(str(key)):
            sanitized[key] = MASK_VALUE
        else:
            sanitized[key] = sanitize_value(value)
    return sanitized


def sanitize_list(data: list) -> list:
    return [sanitize_value(item) for item in data]


def sanitize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return sanitize_dict(value)
    if isinstance(value, list):
        return sanitize_list(value)
    return value


def sanitize_payload(payload: Any) -> Any:
    return sanitize_value(payload)
