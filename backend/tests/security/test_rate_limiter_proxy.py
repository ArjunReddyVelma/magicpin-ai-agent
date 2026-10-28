"""
Route-level security integration tests for proxy-aware rate limiting (SEC-01).

Verifies that auth login and public customer support endpoints correctly resolve
client IP through trusted proxies and reject spoofed headers from untrusted peers.
"""
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.main import app
from backend.app.core.config import settings
from backend.app.core.security import login_rate_limiter
from backend.app.core.support_rate_limiter import support_rate_limiter
from backend.app.models.merchant_profile import MerchantProfile
from backend.app.models.user import User


def test_auth_login_rate_limiting_uses_forwarded_ip_from_trusted_proxy(db_session: Session):
    """
    Verifies that when requests come through a trusted proxy (127.0.0.1),
    failed logins are rate-limited per forwarded IP, so Client A reaching the limit
    does not block Client B using the same proxy.
    """
    # 127.0.0.1 is in default TRUSTED_PROXIES ("127.0.0.1,::1")
    proxy_client = TestClient(app, client=("127.0.0.1", 50000))

    email = f"target_{uuid.uuid4().hex[:8]}@example.com"
    ip_a = "203.0.113.10"
    ip_b = "203.0.113.20"

    # Exhaust rate limit for IP A
    for _ in range(settings.RATE_LIMIT_LOGIN_MAX_ATTEMPTS):
        res = proxy_client.post(
            "/v1/auth/login",
            json={"email": email, "password": "WrongPassword1!"},
            headers={"X-Forwarded-For": ip_a},
        )
        assert res.status_code == 401

    # Next attempt from IP A must be rate-limited (HTTP 429)
    res_a_blocked = proxy_client.post(
        "/v1/auth/login",
        json={"email": email, "password": "WrongPassword1!"},
        headers={"X-Forwarded-For": ip_a},
    )
    assert res_a_blocked.status_code == 429
    assert res_a_blocked.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"

    # Crucial test: Client B arriving through the same proxy with IP B must NOT be blocked
    res_b_allowed = proxy_client.post(
        "/v1/auth/login",
        json={"email": email, "password": "WrongPassword1!"},
        headers={"X-Forwarded-For": ip_b},
    )
    # Status code is 401 (credential failure), NOT 429 (rate-limited)
    assert res_b_allowed.status_code == 401


def test_auth_login_rejects_spoofed_forwarded_header_from_untrusted_peer(db_session: Session):
    """
    Verifies that an untrusted direct peer (198.51.100.99) cannot spoof its IP
    by sending X-Forwarded-For. The rate limiter binds to the untrusted peer IP.
    """
    untrusted_peer_ip = "198.51.100.99"
    direct_client = TestClient(app, client=(untrusted_peer_ip, 50000))

    email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    spoofed_ip = "8.8.8.8"

    # Exhaust rate limit using spoofed header
    for _ in range(settings.RATE_LIMIT_LOGIN_MAX_ATTEMPTS):
        direct_client.post(
            "/v1/auth/login",
            json={"email": email, "password": "WrongPassword1!"},
            headers={"X-Forwarded-For": spoofed_ip},
        )

    # Attempt with a DIFFERENT spoofed header still blocked because peer is 198.51.100.99
    res_blocked = direct_client.post(
        "/v1/auth/login",
        json={"email": email, "password": "WrongPassword1!"},
        headers={"X-Forwarded-For": "1.1.1.1"},
    )
    assert res_blocked.status_code == 429
    assert res_blocked.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"


def test_public_support_session_creation_uses_forwarded_ip_through_trusted_proxy(
    test_merchant: MerchantProfile,
    db_session: Session,
):
    """
    Verifies that public support session creation enforces rate limits per forwarded IP
    when traffic routes through a trusted proxy.
    """
    proxy_client = TestClient(app, client=("127.0.0.1", 50000))
    ip_a = "198.51.100.101"
    ip_b = "198.51.100.102"

    # Limit is 10 sessions per 15 minutes
    for _ in range(support_rate_limiter.session_create_limit):
        res = proxy_client.post(
            "/v1/public/support/sessions",
            json={"merchant_id": str(test_merchant.id), "customer_name": "Customer A"},
            headers={"X-Forwarded-For": ip_a},
        )
        assert res.status_code == 201

    # Next attempt for IP A is 429
    blocked_a = proxy_client.post(
        "/v1/public/support/sessions",
        json={"merchant_id": str(test_merchant.id), "customer_name": "Customer A"},
        headers={"X-Forwarded-For": ip_a},
    )
    assert blocked_a.status_code == 429
    assert blocked_a.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"

    # IP B through the same proxy is NOT blocked
    allowed_b = proxy_client.post(
        "/v1/public/support/sessions",
        json={"merchant_id": str(test_merchant.id), "customer_name": "Customer B"},
        headers={"X-Forwarded-For": ip_b},
    )
    assert allowed_b.status_code == 201
