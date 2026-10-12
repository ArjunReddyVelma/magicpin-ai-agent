import uuid
from fastapi.testclient import TestClient


def test_merchant_profile_crud_and_csrf(client: TestClient):
    email = f"profile_{uuid.uuid4().hex[:8]}@example.com"
    r_reg = client.post("/v1/auth/register", json={
        "email": email,
        "password": "Password123!",
        "full_name": "Profile Owner",
        "business_name": "Initial Store Name",
        "category": "Retail",
        "location": "Indiranagar",
    })
    assert r_reg.status_code == 201
    csrf = r_reg.json()["csrf_token"]
    merchant_id = r_reg.json()["merchant"]["id"]

    # 1. GET profile
    r_get = client.get("/v1/merchant/profile")
    assert r_get.status_code == 200
    p = r_get.json()
    assert p["id"] == merchant_id
    assert p["business_name"] == "Initial Store Name"
    assert p["category"] == "Retail"

    # 2. PATCH profile without CSRF -> 403
    r_no_csrf = client.patch(
        "/v1/merchant/profile",
        json={"business_name": "Updated Store Name"},
    )
    assert r_no_csrf.status_code == 403
    assert r_no_csrf.json()["error"]["code"] == "CSRF_TOKEN_MISSING"

    # 3. PATCH profile with invalid CSRF -> 403
    r_bad_csrf = client.patch(
        "/v1/merchant/profile",
        json={"business_name": "Updated Store Name"},
        headers={"X-CSRF-Token": "bad_csrf_token_value_here"},
    )
    assert r_bad_csrf.status_code == 403
    assert r_bad_csrf.json()["error"]["code"] == "CSRF_TOKEN_INVALID"

    # 4. PATCH profile with valid CSRF -> 200
    r_patch = client.patch(
        "/v1/merchant/profile",
        json={
            "business_name": "Updated Store Name",
            "location": "Koramangala 5th Block",
            "description": "Premium apparel boutique",
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert r_patch.status_code == 200
    updated = r_patch.json()
    assert updated["business_name"] == "Updated Store Name"
    assert updated["location"] == "Koramangala 5th Block"
    assert updated["description"] == "Premium apparel boutique"

    # 5. Confirm via GET
    r_get2 = client.get("/v1/merchant/profile")
    assert r_get2.status_code == 200
    assert r_get2.json()["business_name"] == "Updated Store Name"


def test_merchant_profile_unauthenticated(client: TestClient):
    # Ensure no cookies set
    client.cookies.clear()
    r = client.get("/v1/merchant/profile")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHORIZED"
