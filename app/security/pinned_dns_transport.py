"""
PinnedDNSTransport — protection contre le DNS rebinding.

Attaque DNS rebinding (sans ce fix) :
  1. Attaquant enregistre evil.com → 104.21.x.x (IP externe valide)
  2. Notre SSRF guard valide : 104.21.x.x n'est pas privée → OK
  3. Attaquant change son DNS → 10.0.0.1 (interne, TTL < 1s)
  4. httpx re-résout evil.com au moment de la vraie requête → 10.0.0.1
  5. Accès au réseau interne Kubernetes / metadata cloud

Solution : résoudre le DNS UNE SEULE FOIS à la création du client,
valider l'IP, et épingler cette IP dans le transport.
httpx ne re-résoudra jamais.
"""
from __future__ import annotations

import ipaddress
import socket
from typing import Optional

import httpx

# Ranges interdits — IPs cloud metadata, réseau privé, loopback
_FORBIDDEN_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),   # AWS/GCP/Azure metadata
    ipaddress.ip_network("100.64.0.0/10"),     # Carrier-grade NAT
    ipaddress.ip_network("::1/128"),            # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),           # IPv6 unique local
    ipaddress.ip_network("fe80::/10"),          # IPv6 link-local
]

_BLOCKED_HOSTNAMES = frozenset({
    "localhost", "ip6-localhost", "ip6-loopback",
    "broadcasthost", "0.0.0.0",
})


class SSRFError(ValueError):
    """Raised when a URL resolves to a forbidden (private/internal) address."""


def _is_forbidden_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast:
        return True
    for network in _FORBIDDEN_NETWORKS:
        try:
            if ip in network:
                return True
        except TypeError:
            continue
    return False


def resolve_and_validate(hostname: str) -> str:
    """
    DNS-resolve `hostname`, validate every resolved IP is not private/internal.
    Returns the first valid IP (to use as the pinned address).
    Raises SSRFError on any forbidden address.

    Why validate ALL resolved IPs:
    A hostname can have multiple A/AAAA records. An attacker can include a mix
    of public and private IPs — failing to check all of them would allow bypass.
    """
    if hostname.lower() in _BLOCKED_HOSTNAMES:
        raise SSRFError(f"Hostname {hostname!r} is explicitly forbidden")

    try:
        results = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise SSRFError(f"DNS resolution failed for {hostname!r}: {exc}") from exc

    if not results:
        raise SSRFError(f"No addresses resolved for {hostname!r}")

    resolved_ips: list[str] = []
    for addrinfo in results:
        ip_str = addrinfo[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError as exc:
            raise SSRFError(f"Unparseable IP {ip_str!r} for {hostname!r}") from exc

        if _is_forbidden_ip(ip):
            raise SSRFError(
                f"{hostname!r} resolves to forbidden IP {ip_str!r} "
                "(private network / cloud metadata endpoint)"
            )
        resolved_ips.append(ip_str)

    return resolved_ips[0]


class PinnedDNSTransport(httpx.AsyncHTTPTransport):
    """
    Custom httpx transport that pins connections to a pre-resolved IP address.

    Why subclass AsyncHTTPTransport and not use a proxy:
    - Proxy approach changes the URL → confuses authentication
    - This approach transparently rewrites at the TCP layer
    - Host header and SNI remain as the original hostname → TLS works
    - httpx/httpcore never calls getaddrinfo() again

    Host header flow:
      URL host   = pinned IP    → TCP connects to this address
      Host header = hostname    → HTTP/1.1 virtual-host routing
      SNI         = hostname    → TLS cert verified against original name
    """

    def __init__(self, hostname: str, pinned_ip: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._hostname = hostname
        self._pinned_ip = pinned_ip

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == self._hostname:
            # ① Rewrite URL host → pinned IP (TCP connects here)
            new_url = request.url.copy_with(host=self._pinned_ip)

            # ② Preserve Host header as original hostname
            raw_headers = [
                (k, v) for (k, v) in request.headers.raw
                if k.lower() != b"host"
            ]
            raw_headers.append((b"host", self._hostname.encode("idna")))

            # ③ Override SNI → httpcore uses this for TLS handshake & cert verification
            extensions = dict(request.extensions)
            extensions["sni_hostname"] = self._hostname.encode("ascii")

            request = httpx.Request(
                method=request.method,
                url=new_url,
                headers=raw_headers,
                stream=request.stream,
                extensions=extensions,
            )

        return await super().handle_async_request(request)


def create_pinned_transport(
    hostname: str,
    limits: Optional[httpx.Limits] = None,
) -> PinnedDNSTransport:
    """
    Resolve `hostname` once, validate its IP, return a transport pinned to it.
    Raises SSRFError if the hostname resolves to a forbidden address.
    """
    pinned_ip = resolve_and_validate(hostname)
    return PinnedDNSTransport(
        hostname=hostname,
        pinned_ip=pinned_ip,
        limits=limits
        or httpx.Limits(max_connections=100, max_keepalive_connections=20),
    )
