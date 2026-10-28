"""
Unit tests for centralized client IP extraction and reverse proxy trust model (SEC-01).

Verifies spoof-prevention, untrusted peer boundaries, trusted proxy chains,
right-to-left traversal, and safe handling of malformed forwarding headers.
"""
import pytest
from starlette.datastructures import Headers, Address
from starlette.requests import Request

from backend.app.core.security import get_client_ip, parse_trusted_proxies


def make_request(
    client_host: str = "127.0.0.1",
    client_port: int = 12345,
    headers: dict = None,
) -> Request:
    """Helper to construct lightweight mock Starlette HTTP requests."""
    raw_headers = []
    if headers:
        items = headers if isinstance(headers, list) else headers.items()
        for k, v in items:
            raw_headers.append((k.lower().encode("latin-1"), v.encode("latin-1")))

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/v1/test",
        "headers": raw_headers,
        "client": (client_host, client_port) if client_host is not None else None,
    }
    return Request(scope)


def test_parse_trusted_proxies_valid_cidr_and_single_ips():
    """Verifies parsing of single IPs and CIDR ranges."""
    nets = parse_trusted_proxies("127.0.0.1, ::1, 10.0.0.0/8, 192.168.1.0/24")
    assert len(nets) == 4
    str_nets = [str(n) for n in nets]
    assert "127.0.0.1/32" in str_nets
    assert "::1/128" in str_nets
    assert "10.0.0.0/8" in str_nets
    assert "192.168.1.0/24" in str_nets


def test_direct_connection_untrusted_peer_returns_peer_ip():
    """Direct untrusted client connection returns peer socket IP."""
    req = make_request(client_host="198.51.100.50")
    ip = get_client_ip(req, trusted_proxies="127.0.0.1")
    assert ip == "198.51.100.50"


def test_untrusted_peer_spoofing_header_is_strictly_ignored():
    """
    CRITICAL SECURITY CHECK:
    An untrusted direct client sending X-Forwarded-For cannot spoof its IP.
    The forwarding header MUST be completely ignored.
    """
    req = make_request(
        client_host="198.51.100.50",
        headers={"x-forwarded-for": "8.8.8.8, 1.1.1.1"},
    )
    ip = get_client_ip(req, trusted_proxies="127.0.0.1")
    # Must return the authentic connecting peer IP, NOT the spoofed header
    assert ip == "198.51.100.50"


def test_trusted_proxy_single_hop_extracted():
    """Trusted proxy forwards authentic public client IP."""
    req = make_request(
        client_host="127.0.0.1",
        headers={"x-forwarded-for": "203.0.113.195"},
    )
    ip = get_client_ip(req, trusted_proxies="127.0.0.1")
    assert ip == "203.0.113.195"


def test_trusted_proxy_spoofed_chain_peeled_right_to_left():
    """
    CRITICAL SECURITY CHECK:
    An attacker connects to a trusted proxy supplying a forged X-Forwarded-For header.
    The proxy appends the attacker's true IP (203.0.113.195).
    Right-to-left traversal must pick 203.0.113.195 and ignore the forged hops.
    """
    req = make_request(
        client_host="127.0.0.1",
        headers={"x-forwarded-for": "1.2.3.4, 5.6.7.8, 203.0.113.195"},
    )
    ip = get_client_ip(req, trusted_proxies="127.0.0.1")
    assert ip == "203.0.113.195"


def test_multiple_trusted_proxies_in_chain():
    """
    Client (198.51.100.25) -> Edge Proxy (10.0.0.1) -> Internal Proxy (10.0.0.2).
    Peer is 10.0.0.2. Right-to-left traversal peels 10.0.0.1 and stops at 198.51.100.25.
    """
    req = make_request(
        client_host="10.0.0.2",
        headers={"x-forwarded-for": "198.51.100.25, 10.0.0.1"},
    )
    ip = get_client_ip(req, trusted_proxies="10.0.0.0/8")
    assert ip == "198.51.100.25"


def test_trusted_proxy_ipv6_client():
    """IPv6 client IP extracted cleanly through trusted proxy."""
    req = make_request(
        client_host="::1",
        headers={"x-forwarded-for": "2001:db8:85a3::8a2e:370:7334"},
    )
    ip = get_client_ip(req, trusted_proxies="::1")
    assert ip == "2001:db8:85a3::8a2e:370:7334"


def test_port_stripping_ipv4_and_bracketed_ipv6():
    """Strips port numbers from hops cleanly."""
    req_ipv4 = make_request(
        client_host="127.0.0.1",
        headers={"x-forwarded-for": "203.0.113.50:443"},
    )
    assert get_client_ip(req_ipv4, trusted_proxies="127.0.0.1") == "203.0.113.50"

    req_ipv6 = make_request(
        client_host="127.0.0.1",
        headers={"x-forwarded-for": "[2001:db8::1]:8080"},
    )
    assert get_client_ip(req_ipv6, trusted_proxies="127.0.0.1") == "2001:db8::1"


def test_malformed_headers_fail_safe():
    """
    Malformed headers (SQL injection, script tags, empty entries) do not raise
    exceptions and fall back safely to the peer socket IP.
    """
    req_garbage = make_request(
        client_host="127.0.0.1",
        headers={"x-forwarded-for": "not-an-ip, <script>, , ;;;"},
    )
    # Must not raise; must return peer IP
    assert get_client_ip(req_garbage, trusted_proxies="127.0.0.1") == "127.0.0.1"


def test_missing_or_empty_forwarding_header_returns_peer_ip():
    """Empty or missing X-Forwarded-For header returns trusted proxy peer IP."""
    req_none = make_request(client_host="127.0.0.1", headers=None)
    assert get_client_ip(req_none, trusted_proxies="127.0.0.1") == "127.0.0.1"

    req_empty = make_request(client_host="127.0.0.1", headers={"x-forwarded-for": "   "})
    assert get_client_ip(req_empty, trusted_proxies="127.0.0.1") == "127.0.0.1"


def test_missing_request_client_returns_unknown():
    """Request without client address returns 'unknown'."""
    req = make_request(client_host=None)
    assert get_client_ip(req, trusted_proxies="127.0.0.1") == "unknown"


def test_all_hops_trusted_returns_leftmost():
    """When all hops in the chain are trusted proxies, returns leftmost hop."""
    req = make_request(
        client_host="127.0.0.1",
        headers={"x-forwarded-for": "10.0.0.5, 10.0.0.6"},
    )
    ip = get_client_ip(req, trusted_proxies="127.0.0.1, 10.0.0.0/8")
    assert ip == "10.0.0.5"


def test_trusted_proxy_duplicate_header_lines_joined_right_to_left():
    """
    SECURITY TEST:
    Multiple X-Forwarded-For header lines from downstream proxies must be combined
    so right-to-left traversal reliably examines the proxy-appended hop, rather
    than only examining the first header line.
    """
    req = make_request(
        client_host="127.0.0.1",
        headers=[
            ("X-Forwarded-For", "198.51.100.1"),      # Attacker spoofed header
            ("X-Forwarded-For", "203.0.113.50"),     # Downstream proxy appended line
        ],
    )
    ip = get_client_ip(req, trusted_proxies="127.0.0.1")
    # Traversal from right must encounter 203.0.113.50 first and return it
    assert ip == "203.0.113.50"
