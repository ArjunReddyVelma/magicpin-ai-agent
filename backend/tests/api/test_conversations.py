import time
import uuid
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.repositories.message_repository import MessageRepository


def _register_merchant(client: TestClient, name: str = "Conv Owner"):
    email = f"conv_{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/v1/auth/register", json={
        "email": email,
        "password": "Password123!",
        "full_name": name,
        "business_name": f"{name} Store",
    })
    assert r.status_code == 201
    return r.json()


def test_conversation_crud_and_lifecycle(client: TestClient):
    auth_data = _register_merchant(client, "Lifecycle Conv Owner")
    csrf = auth_data["csrf_token"]

    # 1. Create conversation
    r_create = client.post(
        "/v1/conversations",
        json={"title": "Customer Support Inquiry"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r_create.status_code == 201
    conv = r_create.json()
    conv_id = conv["id"]
    assert conv["title"] == "Customer Support Inquiry"
    assert conv["status"] == "active"

    # 2. Get conversation
    r_get = client.get(f"/v1/conversations/{conv_id}")
    assert r_get.status_code == 200
    assert r_get.json()["id"] == conv_id

    # 3. Patch conversation (rename and archive)
    r_patch = client.patch(
        f"/v1/conversations/{conv_id}",
        json={"title": "Resolved Support Inquiry", "status": "archived"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r_patch.status_code == 200
    updated = r_patch.json()
    assert updated["title"] == "Resolved Support Inquiry"
    assert updated["status"] == "archived"

    # 4. List with status filter
    r_list_archived = client.get("/v1/conversations?status=archived")
    assert r_list_archived.status_code == 200
    assert r_list_archived.json()["total"] == 1
    assert r_list_archived.json()["items"][0]["id"] == conv_id

    r_list_active = client.get("/v1/conversations?status=active")
    assert r_list_active.status_code == 200
    assert r_list_active.json()["total"] == 0

    # 5. Delete conversation
    r_del = client.delete(f"/v1/conversations/{conv_id}", headers={"X-CSRF-Token": csrf})
    assert r_del.status_code == 200
    assert r_del.json()["status"] == "ok"

    # Confirm 404
    r_get_del = client.get(f"/v1/conversations/{conv_id}")
    assert r_get_del.status_code == 404
    assert r_get_del.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"


def test_conversation_messages_pagination_and_deterministic_order(
    client: TestClient, db_session: Session
):
    auth_data = _register_merchant(client, "Message Owner")
    csrf = auth_data["csrf_token"]

    # 1. Create conversation
    r_create = client.post(
        "/v1/conversations",
        json={"title": "Ordering Test"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r_create.status_code == 201
    conv_id = uuid.UUID(r_create.json()["id"])

    # 2. Add sequence of messages via MessageRepository
    msg_repo = MessageRepository(db_session)
    m1 = msg_repo.create(conv_id, role="user", content="Question 1")
    time.sleep(0.01)
    m2 = msg_repo.create(conv_id, role="assistant", content="Answer 1")
    time.sleep(0.01)
    m3 = msg_repo.create(conv_id, role="user", content="Question 2")

    # 3. List messages with page_size=2
    r_page1 = client.get(f"/v1/conversations/{conv_id}/messages?page=1&page_size=2")
    assert r_page1.status_code == 200
    data1 = r_page1.json()
    assert data1["total"] == 3
    assert len(data1["items"]) == 2
    assert data1["items"][0]["id"] == str(m1.id)
    assert data1["items"][1]["id"] == str(m2.id)

    # Page 2
    r_page2 = client.get(f"/v1/conversations/{conv_id}/messages?page=2&page_size=2")
    assert r_page2.status_code == 200
    data2 = r_page2.json()
    assert len(data2["items"]) == 1
    assert data2["items"][0]["id"] == str(m3.id)


def test_conversations_csrf_and_auth_enforcement(client: TestClient):
    auth_data = _register_merchant(client, "Security Conv Owner")
    csrf = auth_data["csrf_token"]

    # Missing CSRF on create -> 403
    r_no_csrf = client.post("/v1/conversations", json={"title": "No CSRF"})
    assert r_no_csrf.status_code == 403
    assert r_no_csrf.json()["error"]["code"] == "CSRF_TOKEN_MISSING"

    # Unauthenticated -> 401
    client.cookies.clear()
    r_unauth = client.get("/v1/conversations")
    assert r_unauth.status_code == 401
    assert r_unauth.json()["error"]["code"] == "UNAUTHORIZED"
