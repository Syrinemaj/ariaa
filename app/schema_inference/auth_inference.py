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
    app_has_session_auth: bool = False,
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

    # No direct evidence in THIS call — common when the HAR was exported by
    # a browser that strips the Cookie/Set-Cookie headers by default (seen
    # on real Edge/Chrome exports: request.cookies stays [] and no
    # Set-Cookie ever appears, even though the app is clearly session-based).
    # If the same run also contains a login/session-management endpoint,
    # report a low-confidence inferred cookie session instead of a flat
    # "no auth" that would be misleading for every other endpoint in the run.
    if app_has_session_auth:
        return AuthInfo(auth_required=True, auth_type="inferred_cookie_session", location="cookie", header_name=None, confidence=0.40)

    return AuthInfo(auth_required=False, confidence=0.0)
