import uuid
from fastapi.testclient import TestClient


def _register_merchant(client: TestClient, name: str = "Context Owner"):
    email = f"ctx_{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/v1/auth/register", json={
        "email": email,
        "password": "Password123!",
        "full_name": name,
        "business_name": f"{name} Store",
    })
    assert r.status_code == 201
    return r.json()


def test_context_item_crud_and_etag_lifecycle(client: TestClient):
    auth_data = _register_merchant(client, "Lifecycle Owner")
    csrf = auth_data["csrf_token"]

    # 1. Create context item
    payload = {
        "item_type": "policy",
        "title": "Return Policy",
        "content": "Full refund within 7 days with original receipt.",
        "is_active": True,
    }
    r_create = client.post("/v1/context", json=payload, headers={"X-CSRF-Token": csrf})
    assert r_create.status_code == 201
    created = r_create.json()
    item_id = created["id"]
    assert created["title"] == "Return Policy"
    assert created["item_type"] == "policy"
    assert created["version"] == 1
    assert r_create.headers.get("ETag") == '"1"'

    # 2. GET item by ID
    r_get = client.get(f"/v1/context/{item_id}")
    assert r_get.status_code == 200
    assert r_get.json()["id"] == item_id
    assert r_get.headers.get("ETag") == '"1"'

    # 3. List items with filtering
    r_list = client.get("/v1/context?item_type=policy&is_active=true")
    assert r_list.status_code == 200
    list_data = r_list.json()
    assert list_data["total"] == 1
    assert list_data["items"][0]["id"] == item_id

    # 4. PATCH item with valid If-Match ETag
    r_patch = client.patch(
        f"/v1/context/{item_id}",
        json={"content": "Updated return policy text: 14 days refund."},
        headers={"X-CSRF-Token": csrf, "If-Match": '"1"'},
    )
    assert r_patch.status_code == 200
    updated = r_patch.json()
    assert updated["content"] == "Updated return policy text: 14 days refund."
    assert updated["version"] == 2
    assert r_patch.headers.get("ETag") == '"2"'

    # 5. DELETE item
    r_del = client.delete(f"/v1/context/{item_id}", headers={"X-CSRF-Token": csrf})
    assert r_del.status_code == 200
    assert r_del.json()["status"] == "ok"

    # Confirm 404
    r_get_del = client.get(f"/v1/context/{item_id}")
    assert r_get_del.status_code == 404
    assert r_get_del.json()["error"]["code"] == "CONTEXT_NOT_FOUND"


def test_context_optimistic_concurrency_conflict(client: TestClient):
    auth_data = _register_merchant(client, "Concurrency Owner")
    csrf = auth_data["csrf_token"]

    r_create = client.post(
        "/v1/context",
        json={
            "item_type": "faq",
            "title": "Store Hours",
            "content": "9 AM to 9 PM daily.",
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert r_create.status_code == 201
    item_id = r_create.json()["id"]

    # 1. Update with stale version in header -> 409 Conflict
    r_conflict_header = client.patch(
        f"/v1/context/{item_id}",
        json={"content": "Conflicting edit"},
        headers={"X-CSRF-Token": csrf, "If-Match": '"99"'},
    )
    assert r_conflict_header.status_code == 409
    assert r_conflict_header.json()["error"]["code"] == "STALE_VERSION_CONFLICT"

    # 2. Update with stale version in body -> 409 Conflict
    r_conflict_body = client.patch(
        f"/v1/context/{item_id}",
        json={"content": "Conflicting edit", "expected_version": 99},
        headers={"X-CSRF-Token": csrf},
    )
    assert r_conflict_body.status_code == 409
    assert r_conflict_body.json()["error"]["code"] == "STALE_VERSION_CONFLICT"

    # 3. Update without version info -> 400 Bad Request
    r_no_ver = client.patch(
        f"/v1/context/{item_id}",
        json={"content": "Missing version"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r_no_ver.status_code == 400
    assert r_no_ver.json()["error"]["code"] == "VERSION_REQUIRED"


def test_context_csrf_and_auth_enforcement(client: TestClient):
    auth_data = _register_merchant(client, "CSRF Owner")
    csrf = auth_data["csrf_token"]

    # Missing CSRF on create -> 403
    r_create_no_csrf = client.post("/v1/context", json={
        "item_type": "business_fact",
        "title": "Founded",
        "content": "Founded in 2021",
    })
    assert r_create_no_csrf.status_code == 403
    assert r_create_no_csrf.json()["error"]["code"] == "CSRF_TOKEN_MISSING"

    # Unauthenticated access -> 401
    client.cookies.clear()
    r_unauth = client.get("/v1/context")
    assert r_unauth.status_code == 401
    assert r_unauth.json()["error"]["code"] == "UNAUTHORIZED"
