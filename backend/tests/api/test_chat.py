import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.main import app
from backend.app.core.dependencies import get_llm_provider
from backend.app.ai.mock_provider import MockLLMProvider
from backend.app.ai.provider import LLMTimeoutError
from backend.app.models.message import Message


@pytest.fixture
def chat_client(client: TestClient):
    mock_provider = MockLLMProvider(
        default_response="According to our policy, cancellation is allowed within 5 minutes."
    )
    app.dependency_overrides[get_llm_provider] = lambda: mock_provider
    yield client, mock_provider
    app.dependency_overrides.pop(get_llm_provider, None)


def test_chat_message_flow_success(chat_client):
    client, mock_provider = chat_client

    # 1. Register & login
    email = f"chat_{uuid.uuid4().hex[:8]}@example.com"
    reg_resp = client.post(
        "/v1/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "Chat Merchant",
            "business_name": "Royal Cafe",
            "category": "Cafe",
        },
    )
    assert reg_resp.status_code == 201
    csrf_token = reg_resp.json()["csrf_token"]
    headers = {"X-CSRF-Token": csrf_token}

    # 2. Add an active context item
    ctx_resp = client.post(
        "/v1/context",
        headers=headers,
        json={
            "item_type": "policy",
            "title": "Cancellation Policy",
            "content": "Orders can be cancelled within 5 minutes of placing.",
            "is_active": True,
        },
    )
    assert ctx_resp.status_code == 201
    ctx_id = ctx_resp.json()["id"]

    # 3. Create conversation
    conv_resp = client.post(
        "/v1/conversations",
        headers=headers,
        json={"title": "Customer Inquiries"},
    )
    assert conv_resp.status_code == 201
    conv_id = conv_resp.json()["id"]

    # 4. Send chat message
    chat_resp = client.post(
        f"/v1/conversations/{conv_id}/messages",
        headers=headers,
        json={"content": "Can a customer cancel their order?"},
    )
    assert chat_resp.status_code == 200
    data = chat_resp.json()

    assert data["user_message"]["role"] == "user"
    assert data["user_message"]["content"] == "Can a customer cancel their order?"
    assert data["user_message"]["status"] == "complete"

    assert data["assistant_message"]["role"] == "assistant"
    assert "cancellation is allowed within 5 minutes" in data["assistant_message"]["content"]
    assert data["assistant_message"]["status"] == "complete"

    assert len(data["context_used"]) >= 1
    assert data["context_used"][0]["context_id"] == ctx_id
    assert data["context_used"][0]["title"] == "Cancellation Policy"

    # Verify message list shows both messages in deterministic order
    list_resp = client.get(f"/v1/conversations/{conv_id}/messages")
    assert list_resp.status_code == 200
    msgs = list_resp.json()["items"]
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"


def test_chat_message_idempotency(chat_client):
    client, mock_provider = chat_client

    email = f"idem_{uuid.uuid4().hex[:8]}@example.com"
    reg_resp = client.post(
        "/v1/auth/register",
        json={"email": email, "password": "Password123!", "full_name": "Idem Owner", "business_name": "Idem Shop"},
    )
    csrf_token = reg_resp.json()["csrf_token"]
    headers = {"X-CSRF-Token": csrf_token}

    conv_resp = client.post("/v1/conversations", headers=headers, json={"title": "Idem Conv"})
    conv_id = conv_resp.json()["id"]

    idem_key = f"key_{uuid.uuid4().hex}"
    req_payload = {"content": "First send", "idempotency_key": idem_key}

    resp1 = client.post(f"/v1/conversations/{conv_id}/messages", headers=headers, json=req_payload)
    assert resp1.status_code == 200
    user_id_1 = resp1.json()["user_message"]["id"]
    asst_id_1 = resp1.json()["assistant_message"]["id"]

    # Resend identical request with same idempotency key
    resp2 = client.post(f"/v1/conversations/{conv_id}/messages", headers=headers, json=req_payload)
    assert resp2.status_code == 200
    user_id_2 = resp2.json()["user_message"]["id"]
    asst_id_2 = resp2.json()["assistant_message"]["id"]

    assert user_id_1 == user_id_2
    assert asst_id_1 == asst_id_2

    # Check database only has 2 messages total, not 4
    list_resp = client.get(f"/v1/conversations/{conv_id}/messages")
    assert len(list_resp.json()["items"]) == 2


def test_chat_provider_failure_preservation_and_retry(chat_client, db_session: Session):
    client, mock_provider = chat_client

    email = f"fail_{uuid.uuid4().hex[:8]}@example.com"
    reg_resp = client.post(
        "/v1/auth/register",
        json={"email": email, "password": "Password123!", "full_name": "Fail Owner", "business_name": "Fail Shop"},
    )
    csrf_token = reg_resp.json()["csrf_token"]
    headers = {"X-CSRF-Token": csrf_token}

    conv_resp = client.post("/v1/conversations", headers=headers, json={"title": "Retry Conv"})
    conv_id = conv_resp.json()["id"]

    # Configure mock provider to fail
    mock_provider.set_should_raise(LLMTimeoutError("Groq gateway timed out"))

    fail_resp = client.post(
        f"/v1/conversations/{conv_id}/messages",
        headers=headers,
        json={"content": "Important user question during outage"},
    )
    assert fail_resp.status_code == 502
    err_body = fail_resp.json()["error"]
    assert err_body["code"] == "LLM_PROVIDER_ERROR"
    failed_msg_id = err_body["details"]["failed_message_id"]

    # Verify user message was preserved in database with status='failed'
    list_resp = client.get(f"/v1/conversations/{conv_id}/messages")
    items = list_resp.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == failed_msg_id
    assert items[0]["role"] == "user"
    assert items[0]["status"] == "failed"

    # Now recover provider and perform retry using retry_message_id
    mock_provider.set_should_raise(None)
    mock_provider.default_response = "Recovered assistant response."

    retry_resp = client.post(
        f"/v1/conversations/{conv_id}/messages",
        headers=headers,
        json={
            "content": "Important user question during outage",
            "retry_message_id": failed_msg_id,
        },
    )
    assert retry_resp.status_code == 200
    retry_data = retry_resp.json()
    assert retry_data["user_message"]["id"] == failed_msg_id
    assert retry_data["user_message"]["status"] == "complete"
    assert retry_data["assistant_message"]["status"] == "complete"

    # Confirm database has only 2 messages (the reused user turn and new assistant turn)
    list_resp2 = client.get(f"/v1/conversations/{conv_id}/messages")
    assert len(list_resp2.json()["items"]) == 2


def test_chat_archived_conversation_rejected(chat_client):
    client, mock_provider = chat_client

    email = f"arch_{uuid.uuid4().hex[:8]}@example.com"
    reg_resp = client.post(
        "/v1/auth/register",
        json={"email": email, "password": "Password123!", "full_name": "Arch Owner", "business_name": "Arch Shop"},
    )
    csrf_token = reg_resp.json()["csrf_token"]
    headers = {"X-CSRF-Token": csrf_token}

    conv_resp = client.post("/v1/conversations", headers=headers, json={"title": "Archived Conv"})
    conv_id = conv_resp.json()["id"]

    # Archive the conversation
    patch_resp = client.patch(
        f"/v1/conversations/{conv_id}",
        headers=headers,
        json={"status": "archived"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == "archived"

    # Attempt to send message
    chat_resp = client.post(
        f"/v1/conversations/{conv_id}/messages",
        headers=headers,
        json={"content": "Hello to archive"},
    )
    assert chat_resp.status_code == 400
    assert chat_resp.json()["error"]["code"] == "CONVERSATION_ARCHIVED"
