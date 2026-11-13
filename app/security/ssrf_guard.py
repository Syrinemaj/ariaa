"""
SSRF Guard — deux couches de protection + normalisation des ports.

Couche 1 : validate_target_url()
  Valide le schéma, normalise le netloc (ports canoniques éliminés),
  vérifie la liste blanche de domaines, résolution DNS initiale.

Couche 2 : create_safe_client()
  Context manager créant un httpx.AsyncClient avec PinnedDNSTransport.
  Le DNS est résolu UNE SEULE FOIS et l'IP est épinglée.

Normalisation des ports :
  https://api.company.com:443 == https://api.company.com
  http://api.company.com:80   == http://api.company.com
  https://api.company.com:8080 ≠ https://api.company.com

  Sans normalisation, ALLOWED_TARGET_DOMAINS="https://api.company.com"
  n'aurait pas bloqué "https://api.company.com:443" → bypass de la whitelist.
"""
from __future__ import annotations

import ipaddress
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional
from urllib.parse import ParseResult, urlparse

import httpx
from fastapi import HTTPException, status

from app.core.config import settings
from app.security.pinned_dns_transport import (
    SSRFError,
    _is_forbidden_ip,
    create_pinned_transport,
)

_BLOCKED_HOSTNAMES = frozenset({
    "localhost", "ip6-localhost", "ip6-loopback",
    "broadcasthost", "0.0.0.0",
})

# Ports canoniques : leur présence explicite est équivalente à leur absence
_CANONICAL_PORTS = {
    "https": 443,
    "http": 80,
}


def normalize_url_base(parsed: ParseResult) -> str:
    """
    Retourne le netloc normalisé en supprimant les ports canoniques.

    https://api.company.com:443 → https://api.company.com
    http://api.company.com:80   → http://api.company.com
    https://api.company.com:8080 → https://api.company.com:8080  (conservé)
    """
    host = parsed.hostname.lower() if parsed.hostname else ""
    port = parsed.port

    # Suppress canonical ports to normalize the key
    if port is not None and _CANONICAL_PORTS.get(parsed.scheme) == port:
        port = None

    if port is not None:
        return f"{parsed.scheme}://{host}:{port}"
    return f"{parsed.scheme}://{host}"


def get_allowed_domains() -> set[str]:
    if not settings.ALLOWED_TARGET_DOMAINS:
        return set()
    return {
        normalize_url_base(urlparse(item.strip().rstrip("/")))
        for item in settings.ALLOWED_TARGET_DOMAINS.split(",")
        if item.strip()
    }


def _parse_and_check_url(url: str) -> tuple[str, str]:
    """
    Parse + validate URL.
    Returns (hostname, normalized_base).
    Raises SSRFError on violation.

    When settings.ALLOW_HTTP_TARGETS=True (dev mode), only the HTTPS-only
    requirement and the configured domain allowlist (ALLOWED_TARGET_DOMAINS,
    an organization-specific business list) are relaxed, so that local mock
    APIs reached by NAME (http://host.docker.internal:9000,
    http://my-mock-api:9000, …) don't need to be added to a production
    allowlist. The blocked-hostname list and the check against literal
    dangerous IP addresses below are NEVER skipped, dev mode or not — they
    are the actual SSRF defense, not a business-configured allowlist.

    Bug fixed here: a prior version also skipped these two checks in dev
    mode, which disabled SSRF protection entirely for any http:// target —
    confirmed by tests/integration/real_db/test_ssrf_guard_integration.py,
    where every dangerous literal (localhost, 127.0.0.1, 169.254.169.254,
    10.0.0.1, 192.168.1.1) passed through unblocked. A resolved DNS NAME
    (host.docker.internal) can still legitimately land on a private IP in
    dev mode — see create_safe_client()'s own dev-mode branch, which never
    resolves the hostname at all — but a literal IP address typed directly
    in the URL has no such legitimate "named local dev host" justification,
    so it is checked unconditionally against the same forbidden ranges used
    by pinned_dns_transport.py.
    """
    parsed = urlparse(url.strip())
    _dev_http = settings.ALLOW_HTTP_TARGETS

    if parsed.scheme not in ("http", "https"):
        raise SSRFError(f"Unsupported URL scheme {parsed.scheme!r}")
    if parsed.scheme == "http" and not _dev_http:
        raise SSRFError("Only HTTPS target URLs are allowed")

    if not parsed.hostname:
        raise SSRFError("Invalid target URL: missing hostname")

    hostname = parsed.hostname.lower()

    if hostname in _BLOCKED_HOSTNAMES:
        raise SSRFError(f"Hostname {hostname!r} is explicitly forbidden")

    try:
        literal_ip = ipaddress.ip_address(hostname)
    except ValueError:
        literal_ip = None
    if literal_ip is not None and _is_forbidden_ip(literal_ip):
        raise SSRFError(
            f"{hostname!r} is a forbidden IP address (private network / "
            "loopback / cloud metadata endpoint)"
        )

    normalized_base = normalize_url_base(parsed)
    if not _dev_http:
        allowed = get_allowed_domains()
        if allowed and normalized_base not in allowed:
            raise SSRFError(f"Domain {normalized_base!r} is not in the allow-list")

    return hostname, normalized_base


# ─── FastAPI layer ────────────────────────────────────────────────────────────

def validate_target_url(url: str) -> None:
    """
    Valide une URL cible au niveau HTTP (lève HTTPException).
    Utiliser create_safe_client() pour les vraies requêtes sortantes.
    """
    try:
        hostname, _ = _parse_and_check_url(url)
        if not settings.ALLOW_HTTP_TARGETS:
            create_pinned_transport(hostname)
    except SSRFError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


# ─── Execution layer ──────────────────────────────────────────────────────────

@asynccontextmanager
async def create_safe_client(
    base_url: str,
    limits: Optional[httpx.Limits] = None,
    timeout: Optional[httpx.Timeout] = None,
) -> AsyncGenerator[httpx.AsyncClient, None]:
    """
    Yield an httpx.AsyncClient with pinned DNS transport.
    TOUTE requête HTTP sortante doit passer par ce context manager.

    In dev mode (ALLOW_HTTP_TARGETS=True) the pinned-DNS transport is replaced
    by a plain transport so that private-IP targets (host.docker.internal, …)
    are reachable without triggering the forbidden-network guard.
    """
    _limits = limits or httpx.Limits(max_connections=100, max_keepalive_connections=20)
    _timeout = timeout or httpx.Timeout(connect=10.0, read=30.0, write=30.0, pool=10.0)

    if settings.ALLOW_HTTP_TARGETS:
        _parse_and_check_url(base_url)  # still validates URL format
        async with httpx.AsyncClient(
            limits=_limits,
            timeout=_timeout,
            base_url=base_url,
        ) as client:
            yield client
        return

    hostname, _ = _parse_and_check_url(base_url)
    transport = create_pinned_transport(hostname, limits=_limits)

    async with httpx.AsyncClient(
        transport=transport,
        timeout=_timeout,
        base_url=base_url,
    ) as client:
        yield client
