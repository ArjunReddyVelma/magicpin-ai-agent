import uuid
from fastapi.testclient import TestClient
from backend.app.core.config import settings
from backend.app.core.security import login_rate_limiter


def test_register_success(client: TestClient):
    unique_email = f"merchant_{uuid.uuid4().hex[:8]}@example.com"
    payload = {
        "email": unique_email,
        "password": "StrongPassword123!",
        "full_name": "Rajesh Kumar",
        "business_name": "Rajesh Electronics",
        "category": "Electronics",
        "location": "Brigade Road, Bangalore",
    }
    response = client.post("/v1/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert "user" in data
    assert "merchant" in data
    assert "csrf_token" in data
    assert data["user"]["email"] == unique_email.lower()
    assert data["user"]["full_name"] == "Rajesh Kumar"
    assert data["merchant"]["business_name"] == "Rajesh Electronics"
    assert len(data["csrf_token"]) == 64

    # Verify session cookie was set
    assert settings.COOKIE_NAME in response.cookies
    cookie_value = response.cookies[settings.COOKIE_NAME]
    assert len(cookie_value) >= 30


def test_register_duplicate_email_rejection(client: TestClient):
    unique_email = f"duplicate_{uuid.uuid4().hex[:8]}@example.com"
    payload = {
        "email": unique_email,
        "password": "StrongPassword123!",
        "full_name": "First User",
        "business_name": "First Store",
    }
    r1 = client.post("/v1/auth/register", json=payload)
    assert r1.status_code == 201

    # Attempt registration with uppercase variant of email
    payload_dup = {
        "email": unique_email.upper(),
        "password": "DifferentPassword123!",
        "full_name": "Second User",
        "business_name": "Second Store",
    }
    r2 = client.post("/v1/auth/register", json=payload_dup)
    assert r2.status_code == 409
    err = r2.json()
    assert err["error"]["code"] == "EMAIL_ALREADY_EXISTS"


def test_register_weak_password_validation(client: TestClient):
    payload = {
        "email": f"weak_{uuid.uuid4().hex[:8]}@example.com",
        "password": "short",  # < 8 chars
        "full_name": "Short Password User",
        "business_name": "Some Store",
    }
    response = client.post("/v1/auth/register", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_login_flow_and_generic_errors(client: TestClient):
    email = f"login_test_{uuid.uuid4().hex[:8]}@example.com"
    password = "CorrectPassword123!"

    # 1. Register
    r_reg = client.post("/v1/auth/register", json={
        "email": email,
        "password": password,
        "full_name": "Login Test Owner",
        "business_name": "Login Test Cafe",
    })
    assert r_reg.status_code == 201

    # 2. Login with wrong password
    r_wrong = client.post("/v1/auth/login", json={
        "email": email,
        "password": "WrongPassword!",
    })
    assert r_wrong.status_code == 401
    assert r_wrong.json()["error"]["code"] == "INVALID_CREDENTIALS"

    # 3. Login with non-existent email (generic error)
    r_no_user = client.post("/v1/auth/login", json={
        "email": "nonexistent@example.com",
        "password": "AnyPassword123!",
    })
    assert r_no_user.status_code == 401
    assert r_no_user.json()["error"]["code"] == "INVALID_CREDENTIALS"

    # 4. Login with correct password
    r_success = client.post("/v1/auth/login", json={
        "email": email,
        "password": password,
    })
    assert r_success.status_code == 200
    data = r_success.json()
    assert data["user"]["email"] == email.lower()
    assert "csrf_token" in data
    assert settings.COOKIE_NAME in r_success.cookies


def test_login_rate_limiting(client: TestClient):
    target_email = f"ratelimit_{uuid.uuid4().hex[:8]}@example.com"
    login_rate_limiter.reset(f"testclient:{target_email.lower()}")

    # 5 failed attempts
    for _ in range(5):
        r = client.post("/v1/auth/login", json={
            "email": target_email,
            "password": "WrongPassword!",
        })
        assert r.status_code == 401

    # 6th attempt should be rate limited
    r_blocked = client.post("/v1/auth/login", json={
        "email": target_email,
        "password": "WrongPassword!",
    })
    assert r_blocked.status_code == 429
    assert r_blocked.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"

    # Clean up rate limiter
    login_rate_limiter.reset(f"testclient:{target_email.lower()}")


def test_get_me_endpoint(client: TestClient):
    # Unauthenticated
    r_unauth = client.get("/v1/auth/me")
    assert r_unauth.status_code == 401
    assert r_unauth.json()["error"]["code"] == "UNAUTHORIZED"

    # Authenticated
    email = f"me_test_{uuid.uuid4().hex[:8]}@example.com"
    r_reg = client.post("/v1/auth/register", json={
        "email": email,
        "password": "Password123!",
        "full_name": "Me User",
        "business_name": "Me Business",
    })
    assert r_reg.status_code == 201

    r_me = client.get("/v1/auth/me")
    assert r_me.status_code == 200
    me_data = r_me.json()
    assert me_data["user"]["email"] == email
    assert me_data["merchant"]["business_name"] == "Me Business"


def test_logout_and_session_revocation(client: TestClient):
    email = f"logout_{uuid.uuid4().hex[:8]}@example.com"
    r_reg = client.post("/v1/auth/register", json={
        "email": email,
        "password": "Password123!",
        "full_name": "Logout User",
        "business_name": "Logout Business",
    })
    csrf = r_reg.json()["csrf_token"]

    # Attempt logout without CSRF -> 403 Forbidden
    r_no_csrf = client.post("/v1/auth/logout")
    assert r_no_csrf.status_code == 403
    assert r_no_csrf.json()["error"]["code"] == "CSRF_TOKEN_MISSING"

    # Logout with CSRF
    r_logout = client.post("/v1/auth/logout", headers={"X-CSRF-Token": csrf})
    assert r_logout.status_code == 200
    assert r_logout.json() == {"status": "ok"}

    # Subsequent request with old cookie should fail
    r_me = client.get("/v1/auth/me")
    assert r_me.status_code == 401


def test_session_rotation_on_refresh(client: TestClient):
    email = f"refresh_{uuid.uuid4().hex[:8]}@example.com"
    r_reg = client.post("/v1/auth/register", json={
        "email": email,
        "password": "Password123!",
        "full_name": "Refresh User",
        "business_name": "Refresh Business",
    })
    old_cookie = client.cookies.get(settings.COOKIE_NAME)
    csrf = r_reg.json()["csrf_token"]

    # Call /v1/auth/refresh
    r_ref = client.post("/v1/auth/refresh", headers={"X-CSRF-Token": csrf})
    assert r_ref.status_code == 200
    new_csrf = r_ref.json()["csrf_token"]
    assert new_csrf != csrf
    new_cookie = client.cookies.get(settings.COOKIE_NAME)
    assert new_cookie != old_cookie

    # Request with new cookie works
    r_me = client.get("/v1/auth/me")
    assert r_me.status_code == 200

    # Old cookie is revoked in DB and rejected
    client.cookies.set(settings.COOKIE_NAME, old_cookie)
    r_old = client.get("/v1/auth/me")
    assert r_old.status_code == 401
    assert r_old.json()["error"]["code"] == "UNAUTHORIZED"


def test_account_deletion_flow(client: TestClient):
    email = f"delete_{uuid.uuid4().hex[:8]}@example.com"
    password = "DeletePassword123!"
    r_reg = client.post("/v1/auth/register", json={
        "email": email,
        "password": password,
        "full_name": "Delete User",
        "business_name": "Delete Business",
    })
    csrf = r_reg.json()["csrf_token"]

    # Delete with wrong password
    r_wrong_pw = client.request(
        "DELETE",
        "/v1/auth/account",
        json={"password": "IncorrectPassword!"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r_wrong_pw.status_code == 401
    assert r_wrong_pw.json()["error"]["code"] == "INVALID_PASSWORD"

    # Delete with correct password
    r_del = client.request(
        "DELETE",
        "/v1/auth/account",
        json={"password": password},
        headers={"X-CSRF-Token": csrf},
    )
    assert r_del.status_code == 200
    assert r_del.json()["status"] == "ok"

    # Subsequent access fails
    r_me = client.get("/v1/auth/me")
    assert r_me.status_code == 401
