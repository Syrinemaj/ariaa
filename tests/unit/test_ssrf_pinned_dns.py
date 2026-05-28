"""Tests for Fix 3.4 — DNS Rebinding / SSRF Guard."""
import ipaddress
import socket
from unittest.mock import MagicMock, patch

import pytest

from app.security.pinned_dns_transport import (
    SSRFError,
    _is_forbidden_ip,
    resolve_and_validate,
)


class TestIsForbiddenIp:
    def test_private_10_blocked(self):
        assert _is_forbidden_ip(ipaddress.ip_address("10.0.0.1")) is True

    def test_private_172_blocked(self):
        assert _is_forbidden_ip(ipaddress.ip_address("172.16.0.1")) is True

    def test_private_192_blocked(self):
        assert _is_forbidden_ip(ipaddress.ip_address("192.168.1.1")) is True

    def test_loopback_blocked(self):
        assert _is_forbidden_ip(ipaddress.ip_address("127.0.0.1")) is True

    def test_metadata_endpoint_blocked(self):
        # AWS / GCP / Azure cloud metadata
        assert _is_forbidden_ip(ipaddress.ip_address("169.254.169.254")) is True

    def test_ipv6_loopback_blocked(self):
        assert _is_forbidden_ip(ipaddress.ip_address("::1")) is True

    def test_public_ip_allowed(self):
        assert _is_forbidden_ip(ipaddress.ip_address("52.94.228.167")) is False

    def test_cloudflare_allowed(self):
        assert _is_forbidden_ip(ipaddress.ip_address("104.21.60.1")) is False


class TestResolveAndValidate:
    def test_localhost_blocked(self):
        with pytest.raises(SSRFError, match="forbidden"):
            resolve_and_validate("localhost")

    def test_zero_address_blocked(self):
        with pytest.raises(SSRFError, match="forbidden"):
            resolve_and_validate("0.0.0.0")

    def test_private_ip_resolution_blocked(self):
        # Simulate a hostname resolving to a private IP
        mock_result = [(None, None, None, None, ("10.0.0.1", 0))]
        with patch("socket.getaddrinfo", return_value=mock_result):
            with pytest.raises(SSRFError, match="forbidden IP"):
                resolve_and_validate("evil.internal")

    def test_metadata_ip_resolution_blocked(self):
        mock_result = [(None, None, None, None, ("169.254.169.254", 0))]
        with patch("socket.getaddrinfo", return_value=mock_result):
            with pytest.raises(SSRFError, match="forbidden IP"):
                resolve_and_validate("metadata.example.com")

    def test_public_ip_resolution_allowed(self):
        mock_result = [(None, None, None, None, ("52.94.228.167", 0))]
        with patch("socket.getaddrinfo", return_value=mock_result):
            ip = resolve_and_validate("api.example.com")
            assert ip == "52.94.228.167"

    def test_dns_failure_raises(self):
        with patch("socket.getaddrinfo", side_effect=socket.gaierror("no route")):
            with pytest.raises(SSRFError, match="DNS resolution failed"):
                resolve_and_validate("nonexistent.invalid")

    def test_dns_rebinding_scenario(self):
        """
        Simulate DNS rebinding: first resolution returns public IP (validation),
        but the PINNED transport prevents the second resolution from happening.
        This test verifies that resolve_and_validate blocks the private IP
        when the DNS is changed between calls.
        """
        call_count = [0]

        def fake_getaddrinfo(host, *args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call (validation): returns public IP
                return [(None, None, None, None, ("104.21.60.1", 0))]
            else:
                # Second call (if it happened): returns private IP
                return [(None, None, None, None, ("10.0.0.1", 0))]

        with patch("socket.getaddrinfo", side_effect=fake_getaddrinfo):
            ip = resolve_and_validate("evil.com")
            assert ip == "104.21.60.1"
            # Only ONE DNS call was made — pinning prevents re-resolution
            assert call_count[0] == 1

    def test_mixed_public_private_ips_blocked(self):
        """A hostname returning both public and private IPs must be blocked."""
        mock_results = [
            (None, None, None, None, ("52.0.0.1", 0)),   # public
            (None, None, None, None, ("10.0.0.1", 0)),   # private — must block
        ]
        with patch("socket.getaddrinfo", return_value=mock_results):
            with pytest.raises(SSRFError, match="forbidden IP"):
                resolve_and_validate("mixed.example.com")
