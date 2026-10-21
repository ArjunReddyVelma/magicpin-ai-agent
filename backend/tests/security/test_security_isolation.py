import uuid
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.security import hash_session_token
from backend.app.models.user_session import UserSession


def test_cross_merchant_session_isolation(client: TestClient):
    """
    SECURITY TEST: Proves that merchant identity is derived strictly from
    the authenticated session, and cannot be spoofed across tenants.
    """
    # 1. Register Merchant A
    email_a = f"tenant_a_{uuid.uuid4().hex[:8]}@example.com"
    r_a = client.post("/v1/auth/register", json={
        "email": email_a,
        "password": "PasswordA123!",
        "full_name": "Merchant Owner A",
        "business_name": "Merchant Business A",
    })
    assert r_a.status_code == 201
    cookie_a = client.cookies.get(settings.COOKIE_NAME)
    merchant_id_a = r_a.json()["merchant"]["id"]

    # 2. Register Merchant B
    email_b = f"tenant_b_{uuid.uuid4().hex[:8]}@example.com"
    r_b = client.post("/v1/auth/register", json={
        "email": email_b,
        "password": "PasswordB123!",
        "full_name": "Merchant Owner B",
        "business_name": "Merchant Business B",
    })
    assert r_b.status_code == 201
    cookie_b = client.cookies.get(settings.COOKIE_NAME)
    csrf_b = r_b.json()["csrf_token"]
    merchant_id_b = r_b.json()["merchant"]["id"]

    assert merchant_id_a != merchant_id_b

    # 3. Using Merchant B's session, profile returned MUST be Merchant B
    r_b_prof = client.get("/v1/merchant/profile")
    assert r_b_prof.status_code == 200
    assert r_b_prof.json()["id"] == merchant_id_b
    assert r_b_prof.json()["business_name"] == "Merchant Business B"

    # 4. Switch back to Merchant A's cookie
    client.cookies.clear()
    client.cookies.set(settings.COOKIE_NAME, cookie_a)
    r_a_prof = client.get("/v1/merchant/profile")
    assert r_a_prof.status_code == 200
    assert r_a_prof.json()["id"] == merchant_id_a
    assert r_a_prof.json()["business_name"] == "Merchant Business A"

    # 5. Even if Merchant A supplies merchant_id_b in request body,
    # server ignores it and only mutates Merchant A's profile
    r_spoof = client.patch(
        "/v1/merchant/profile",
        json={
            "business_name": "Merchant A Tampered Name",
            "merchant_id": merchant_id_b,  # Hostile injection attempt
        },
        headers={"X-CSRF-Token": r_a.json()["csrf_token"]},
    )
    assert r_spoof.status_code == 200
    assert r_spoof.json()["id"] == merchant_id_a
    assert r_spoof.json()["business_name"] == "Merchant A Tampered Name"

    # Confirm Merchant B's profile was NOT altered
    client.cookies.clear()
    client.cookies.set(settings.COOKIE_NAME, cookie_b)
    r_b_verify = client.get("/v1/merchant/profile")
    assert r_b_verify.json()["business_name"] == "Merchant Business B"


def test_csrf_token_cross_session_binding(client: TestClient):
    """
    SECURITY TEST: Proves that a valid CSRF token from Session A
    cannot be used to authorize an action for Session B.
    """
    # Register User A
    r_a = client.post("/v1/auth/register", json={
        "email": f"csrf_a_{uuid.uuid4().hex[:8]}@example.com",
        "password": "Password123!",
        "full_name": "User A",
        "business_name": "Biz A",
    })
    csrf_a = r_a.json()["csrf_token"]

    # Register User B
    r_b = client.post("/v1/auth/register", json={
        "email": f"csrf_b_{uuid.uuid4().hex[:8]}@example.com",
        "password": "Password123!",
        "full_name": "User B",
        "business_name": "Biz B",
    })
    # Client now holds User B's session cookie

    # Attempt to update User B's profile using User A's CSRF token
    r_cross = client.patch(
        "/v1/merchant/profile",
        json={"business_name": "Attacked Name"},
        headers={"X-CSRF-Token": csrf_a},
    )
    assert r_cross.status_code == 403
    assert r_cross.json()["error"]["code"] == "CSRF_TOKEN_INVALID"


def test_session_expiration_and_revocation_enforcement(client: TestClient, db_session: Session):
    """
    SECURITY TEST: Proves expired and revoked sessions are unconditionally rejected.
    """
    email = f"session_test_{uuid.uuid4().hex[:8]}@example.com"
    r_reg = client.post("/v1/auth/register", json={
        "email": email,
        "password": "Password123!",
        "full_name": "Expiry Test",
        "business_name": "Expiry Cafe",
    })
    assert r_reg.status_code == 201
    cookie = client.cookies.get(settings.COOKIE_NAME)
    token_hash = hash_session_token(cookie)

    # 1. Verify working session
    assert client.get("/v1/auth/me").status_code == 200

    # 2. Manually expire session in DB
    session_row = db_session.query(UserSession).filter(UserSession.token_hash == token_hash).first()
    assert session_row is not None
    session_row.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db_session.commit()

    # Request with expired session must fail
    r_expired = client.get("/v1/auth/me")
    assert r_expired.status_code == 401
    assert "expired" in r_expired.json()["error"]["message"].lower()

    # 3. Manually revoke session in DB
    session_row.expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    session_row.revoked_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    db_session.commit()

    # Request with revoked session must fail
    r_revoked = client.get("/v1/auth/me")
    assert r_revoked.status_code == 401
    assert "revoked" in r_revoked.json()["error"]["message"].lower()
