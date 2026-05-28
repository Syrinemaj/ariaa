from typing import Dict, Optional

from app.schema_inference.models import AuthInfo


AUTH_HEADER_NAMES = {
    "authorization",
    "x-api-key",
    "api-key",
    "apikey",
    "x-auth-token",
}


def infer_auth_from_headers(
    request_headers: Optional[Dict[str, str]] = None,
    response_headers: Optional[Dict[str, str]] = None,
) -> AuthInfo:
    request_headers = request_headers or {}
    response_headers = response_headers or {}

    normalized = {k.lower(): v for k, v in request_headers.items()}

    authorization = normalized.get("authorization")
    if authorization:
        lower = authorization.lower()
        if lower.startswith("bearer "):
            return AuthInfo(auth_required=True, auth_type="bearer_token", location="header", header_name="authorization", confidence=0.95)
        if lower.startswith("basic "):
            return AuthInfo(auth_required=True, auth_type="basic_auth", location="header", header_name="authorization", confidence=0.95)
        return AuthInfo(auth_required=True, auth_type="authorization_header", location="header", header_name="authorization", confidence=0.85)

    for header_name in AUTH_HEADER_NAMES:
        if header_name in normalized:
            if header_name in {"x-api-key", "api-key", "apikey"}:
                return AuthInfo(auth_required=True, auth_type="api_key", location="header", header_name=header_name, confidence=0.90)
            return AuthInfo(auth_required=True, auth_type="token", location="header", header_name=header_name, confidence=0.85)

    if normalized.get("cookie"):
        return AuthInfo(auth_required=True, auth_type="cookie_session", location="cookie", header_name="cookie", confidence=0.80)

    normalized_response = {k.lower(): v for k, v in response_headers.items()}
    if normalized_response.get("www-authenticate"):
        return AuthInfo(auth_required=True, auth_type="www_authenticate", location="response_header", header_name="www-authenticate", confidence=0.75)

    return AuthInfo(auth_required=False, confidence=0.0)
