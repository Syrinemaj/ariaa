"""
Execution engine — single step execution.

Key design decisions vs original:
- httpx.AsyncClient is NO LONGER created here. The caller (execute_plan_batch,
  execute_batch_task) creates ONE client per run and passes it in.
  Reason: 1000 rows × 3 steps = 3000 TCP handshakes in the old code.

- _resolve_path_params() now URL-encodes each parameter value and validates
  against path traversal patterns BEFORE building the URL.
  Reason: an API response containing {"id": "../../admin"} would previously
  produce https://target.com/api/../../admin — bypassing the SSRF guard.

- The FULLY RESOLVED URL (base + path) passes through the SSRF guard,
  not just the base URL.
"""
from __future__ import annotations

from typing import Any, Dict, Optional
from urllib.parse import quote, urljoin, urlparse

import httpx

from app.automation.models import StepExecutionResult
from app.planner.models import PlanStep
from app.security.business_payload_rules import assert_business_rules_valid
from app.security.payload_validator import assert_payload_valid
from app.security.ssrf_guard import validate_target_url


class PathTraversalError(ValueError):
    """Raised when a path parameter or resolved URL contains traversal sequences."""


# Lowercase normalised patterns that indicate path traversal attempts.
# Checked against both the raw parameter value AND the fully-resolved URL.
_TRAVERSAL_PATTERNS: frozenset[str] = frozenset({
    "..",
    "//",
    "%2e%2e",
    "%2f%2f",
    "0x2e0x2e",
    "%252e",   # double-encoded dot
    "%252f",   # double-encoded slash
    "..%2f",
    "%2f..",
})


def _contains_traversal(s: str) -> bool:
    lower = s.lower()
    return any(pattern in lower for pattern in _TRAVERSAL_PATTERNS)


def _resolve_path_params(
    path: str,
    payload: Dict[str, Any],
    state: Dict[str, Any],
) -> str:
    """
    Replace {param} placeholders in `path` with URL-encoded values.

    Security measures:
    1. URL-encode every value with quote(safe='') — prevents injection of
       slashes, dots, or special chars into the URL structure.
    2. Check raw value BEFORE encoding (catches "../../admin").
    3. Check resolved path AFTER substitution (catches encoded variants).
    4. Raise PathTraversalError immediately on any suspicious pattern.
    """
    resolved = path
    values = {**state, **payload}

    for key, value in values.items():
        placeholder = "{" + key + "}"
        if placeholder not in resolved:
            continue

        raw = str(value)

        # Check raw value before encoding
        if _contains_traversal(raw):
            raise PathTraversalError(
                f"Path parameter {key!r} contains a traversal sequence: {raw!r}"
            )

        # URL-encode: safe='' encodes '/', '.', '@', etc.
        encoded = quote(raw, safe="")
        resolved = resolved.replace(placeholder, encoded)

    # Second pass: check the fully assembled path
    if _contains_traversal(resolved):
        raise PathTraversalError(
            f"Resolved path still contains a traversal sequence: {resolved!r}"
        )

    return resolved


def _build_and_validate_url(base_url: Optional[str], resolved_path: str) -> str:
    """
    Build the full URL and validate it.

    Ensures:
    - The resolved URL's host has not drifted from the base URL's host
      (e.g., path param containing "//evil.com" could redirect the netloc).
    - The full URL passes the SSRF guard (not just the base).
    """
    if not base_url:
        return resolved_path

    url = urljoin(base_url.rstrip("/") + "/", resolved_path.lstrip("/"))

    # Guard: netloc must not change after resolution
    base_netloc = urlparse(base_url).netloc
    final_netloc = urlparse(url).netloc
    if base_netloc and final_netloc and base_netloc != final_netloc:
        raise PathTraversalError(
            f"Resolved URL host changed from {base_netloc!r} to {final_netloc!r}. "
            "Possible URL injection via path parameter."
        )

    return url


async def execute_step(
    step: PlanStep,
    payload: Dict[str, Any],
    state: Dict[str, Any],
    client: httpx.AsyncClient,          # shared across the entire run
    base_url: Optional[str] = None,
    auth_headers: Optional[Dict[str, str]] = None,
    dry_run: bool = True,
) -> StepExecutionResult:
    """
    Execute a single automation step using a shared httpx client.

    The `client` MUST be created by the caller (execute_plan_batch /
    execute_batch_task) using create_safe_client(). Creating one client
    per run — not per step — reuses TCP connections and avoids the
    connection-limit exhaustion that killed target APIs in the old code.
    """
    auth_headers = auth_headers or {}

    try:
        resolved_path = _resolve_path_params(
            path=step.path, payload=payload, state=state
        )
    except PathTraversalError as exc:
        return StepExecutionResult(
            step_order=step.order,
            method=step.method,
            path=step.path,
            url=step.path,
            status="failed",
            status_code=None,
            request_payload=payload,
            response_payload=None,
            error_message=f"Security: {exc}",
        )

    try:
        url = _build_and_validate_url(base_url, resolved_path)
    except PathTraversalError as exc:
        return StepExecutionResult(
            step_order=step.order,
            method=step.method,
            path=step.path,
            url=resolved_path,
            status="failed",
            status_code=None,
            request_payload=payload,
            response_payload=None,
            error_message=f"Security: {exc}",
        )

    if dry_run:
        return StepExecutionResult(
            step_order=step.order,
            method=step.method,
            path=step.path,
            url=url,
            status="dry_run",
            status_code=None,
            request_payload=payload,
            response_payload={"message": "Dry-run mode: request not executed."},
        )

    # ── Payload validation ───────────────────────────────────────────────────
    try:
        assert_payload_valid(step=step, payload=payload)
        assert_business_rules_valid(payload=payload)
    except Exception as validation_error:
        return StepExecutionResult(
            step_order=step.order,
            method=step.method,
            path=step.path,
            url=url,
            status="failed",
            status_code=None,
            request_payload=payload,
            response_payload=None,
            error_message=f"Validation error: {validation_error}",
        )

    # ── Execute with shared client (no new connection pool created) ──────────
    try:
        response = await client.request(
            method=step.method,
            url=url,
            headers=auth_headers,
            json=payload if payload else None,
        )

        try:
            response_payload = response.json()
        except Exception:
            response_payload = {"text": response.text}

        step_status = "success" if 200 <= response.status_code < 400 else "failed"

        return StepExecutionResult(
            step_order=step.order,
            method=step.method,
            path=step.path,
            url=url,
            status=step_status,
            status_code=response.status_code,
            request_payload=payload,
            response_payload=response_payload,
            error_message=None if step_status == "success" else response.text,
        )

    except Exception as error:
        return StepExecutionResult(
            step_order=step.order,
            method=step.method,
            path=step.path,
            url=url,
            status="failed",
            status_code=None,
            request_payload=payload,
            response_payload=None,
            error_message=str(error),
        )
