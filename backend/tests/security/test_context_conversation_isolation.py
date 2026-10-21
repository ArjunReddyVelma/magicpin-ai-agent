import uuid
from fastapi.testclient import TestClient
from backend.app.core.config import settings


def _register(client: TestClient, prefix: str):
    email = f"{prefix}_{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/v1/auth/register", json={
        "email": email,
        "password": "Password123!",
        "full_name": f"{prefix} Owner",
        "business_name": f"{prefix} Biz",
    })
    assert r.status_code == 201
    return r.json(), client.cookies.get(settings.COOKIE_NAME)


def test_cross_merchant_context_isolation(client: TestClient):
    """
    SECURITY TEST: Proves that Tenant B cannot read, update, delete,
    or list context items belonging to Tenant A.
    """
    # 1. Register Merchant A and create a secret policy item
    auth_a, cookie_a = _register(client, "tenant_a")
    csrf_a = auth_a["csrf_token"]

    r_item_a = client.post(
        "/v1/context",
        json={
            "item_type": "policy",
            "title": "Merchant A Confidential Policy",
            "content": "Secret internal guidelines for Merchant A only.",
        },
        headers={"X-CSRF-Token": csrf_a},
    )
    assert r_item_a.status_code == 201
    item_id_a = r_item_a.json()["id"]

    # 2. Register Merchant B
    auth_b, cookie_b = _register(client, "tenant_b")
    csrf_b = auth_b["csrf_token"]

    # Merchant B tries to GET Merchant A's item -> 404
    r_b_get = client.get(f"/v1/context/{item_id_a}")
    assert r_b_get.status_code == 404
    assert r_b_get.json()["error"]["code"] == "CONTEXT_NOT_FOUND"

    # Merchant B tries to PATCH Merchant A's item -> 404
    r_b_patch = client.patch(
        f"/v1/context/{item_id_a}",
        json={"content": "Malicious override by Tenant B"},
        headers={"X-CSRF-Token": csrf_b, "If-Match": '"1"'},
    )
    assert r_b_patch.status_code == 404

    # Merchant B tries to DELETE Merchant A's item -> 404
    r_b_del = client.delete(f"/v1/context/{item_id_a}", headers={"X-CSRF-Token": csrf_b})
    assert r_b_del.status_code == 404

    # Merchant B listing items should see empty list
    r_b_list = client.get("/v1/context")
    assert r_b_list.status_code == 200
    assert r_b_list.json()["total"] == 0

    # 3. Confirm Merchant A's data was completely untouched
    client.cookies.clear()
    client.cookies.set(settings.COOKIE_NAME, cookie_a)
    r_a_verify = client.get(f"/v1/context/{item_id_a}")
    assert r_a_verify.status_code == 200
    assert r_a_verify.json()["content"] == "Secret internal guidelines for Merchant A only."


def test_cross_merchant_conversation_isolation(client: TestClient):
    """
    SECURITY TEST: Proves that Tenant B cannot access, mutate, delete,
    or read messages of conversations belonging to Tenant A.
    """
    # 1. Register Merchant A and create private conversation
    auth_a, cookie_a = _register(client, "tenant_a_conv")
    csrf_a = auth_a["csrf_token"]

    r_conv_a = client.post(
        "/v1/conversations",
        json={"title": "Private Merchant A Support"},
        headers={"X-CSRF-Token": csrf_a},
    )
    assert r_conv_a.status_code == 201
    conv_id_a = r_conv_a.json()["id"]

    # 2. Register Merchant B
    auth_b, cookie_b = _register(client, "tenant_b_conv")
    csrf_b = auth_b["csrf_token"]

    # Merchant B tries to GET Merchant A's conversation -> 404
    r_b_get = client.get(f"/v1/conversations/{conv_id_a}")
    assert r_b_get.status_code == 404
    assert r_b_get.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"

    # Merchant B tries to PATCH Merchant A's conversation -> 404
    r_b_patch = client.patch(
        f"/v1/conversations/{conv_id_a}",
        json={"title": "Hijacked Title"},
        headers={"X-CSRF-Token": csrf_b},
    )
    assert r_b_patch.status_code == 404

    # Merchant B tries to DELETE Merchant A's conversation -> 404
    r_b_del = client.delete(f"/v1/conversations/{conv_id_a}", headers={"X-CSRF-Token": csrf_b})
    assert r_b_del.status_code == 404

    # Merchant B tries to read messages -> 404
    r_b_msgs = client.get(f"/v1/conversations/{conv_id_a}/messages")
    assert r_b_msgs.status_code == 404

    # Merchant B listing conversations should NOT include Merchant A's
    r_b_list = client.get("/v1/conversations")
    assert r_b_list.status_code == 200
    assert r_b_list.json()["total"] == 0


def test_data_persistence_across_sessions(client: TestClient):
    """
    PERSISTENCE TEST: Proves that context and conversations persist in PostgreSQL
    and remain intact across session logout and re-login.
    """
    email = f"persist_{uuid.uuid4().hex[:8]}@example.com"
    password = "PersistPassword123!"

    # 1. Register
    r_reg = client.post("/v1/auth/register", json={
        "email": email,
        "password": password,
        "full_name": "Persistent Owner",
        "business_name": "Persistent Retail",
    })
    csrf = r_reg.json()["csrf_token"]

    # 2. Create context item and conversation
    r_ctx = client.post(
        "/v1/context",
        json={"item_type": "faq", "title": "Parking Info", "content": "Free customer parking."},
        headers={"X-CSRF-Token": csrf},
    )
    assert r_ctx.status_code == 201
    ctx_id = r_ctx.json()["id"]

    r_conv = client.post(
        "/v1/conversations",
        json={"title": "Inquiry 101"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r_conv.status_code == 201
    conv_id = r_conv.json()["id"]

    # 3. Log out
    client.post("/v1/auth/logout", headers={"X-CSRF-Token": csrf})

    # 4. Log back in with fresh session
    r_login = client.post("/v1/auth/login", json={"email": email, "password": password})
    assert r_login.status_code == 200

    # 5. Verify records still exist in PostgreSQL
    r_ctx_check = client.get(f"/v1/context/{ctx_id}")
    assert r_ctx_check.status_code == 200
    assert r_ctx_check.json()["title"] == "Parking Info"

    r_conv_check = client.get(f"/v1/conversations/{conv_id}")
    assert r_conv_check.status_code == 200
    assert r_conv_check.json()["title"] == "Inquiry 101"
