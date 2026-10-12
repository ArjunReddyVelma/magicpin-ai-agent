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


def test_repeated_retry_failure_lifecycle(chat_client):
    """
    Proves full lifecycle: initial failure -> retry 1 fails (remains failed) -> retry 2 succeeds.
    Verifies message is never marked complete before actual provider success.
    """
    client, mock_provider = chat_client

    email = f"rep_{uuid.uuid4().hex[:8]}@example.com"
    reg_resp = client.post(
        "/v1/auth/register",
        json={"email": email, "password": "Password123!", "full_name": "Rep Owner", "business_name": "Rep Shop"},
    )
    headers = {"X-CSRF-Token": reg_resp.json()["csrf_token"]}
    conv_id = client.post("/v1/conversations", headers=headers, json={"title": "Rep Conv"}).json()["id"]

    # 1. Initial attempt fails
    mock_provider.set_should_raise(LLMTimeoutError("First timeout"))
    resp1 = client.post(f"/v1/conversations/{conv_id}/messages", headers=headers, json={"content": "Question"})
    assert resp1.status_code == 502
    failed_id = resp1.json()["error"]["details"]["failed_message_id"]

    # Verify status in DB is failed
    msgs1 = client.get(f"/v1/conversations/{conv_id}/messages").json()["items"]
    assert len(msgs1) == 1
    assert msgs1[0]["id"] == failed_id
    assert msgs1[0]["status"] == "failed"

    # 2. Retry 1 fails again
    mock_provider.set_should_raise(LLMTimeoutError("Second timeout"))
    resp2 = client.post(
        f"/v1/conversations/{conv_id}/messages",
        headers=headers,
        json={"content": "Question retry", "retry_message_id": failed_id},
    )
    assert resp2.status_code == 502
    assert resp2.json()["error"]["code"] == "LLM_PROVIDER_ERROR"
    assert resp2.json()["error"]["details"]["failed_message_id"] == failed_id

    # Verify status in DB is STILL failed (never marked complete prematurely)
    msgs2 = client.get(f"/v1/conversations/{conv_id}/messages").json()["items"]
    assert len(msgs2) == 1
    assert msgs2[0]["id"] == failed_id
    assert msgs2[0]["status"] == "failed"

    # 3. Retry 2 succeeds
    mock_provider.set_should_raise(None)
    mock_provider.default_response = "Success after retries"
    resp3 = client.post(
        f"/v1/conversations/{conv_id}/messages",
        headers=headers,
        json={"content": "Question retry", "retry_message_id": failed_id},
    )
    assert resp3.status_code == 200
    assert resp3.json()["user_message"]["id"] == failed_id
    assert resp3.json()["user_message"]["status"] == "complete"
    assert resp3.json()["assistant_message"]["status"] == "complete"

    # Final DB check: exactly 2 messages, both complete
    msgs3 = client.get(f"/v1/conversations/{conv_id}/messages").json()["items"]
    assert len(msgs3) == 2
    assert msgs3[0]["status"] == "complete"
    assert msgs3[1]["status"] == "complete"


def test_invalid_retry_targets(chat_client):
    """
    Proves invalid retry attempts are strictly rejected:
    - Non-existent message -> 404
    - Already completed message -> 409
    - Message from another conversation -> 404
    """
    client, mock_provider = chat_client

    email = f"target_{uuid.uuid4().hex[:8]}@example.com"
    reg_resp = client.post(
        "/v1/auth/register",
        json={"email": email, "password": "Password123!", "full_name": "Target Owner", "business_name": "Target Shop"},
    )
    headers = {"X-CSRF-Token": reg_resp.json()["csrf_token"]}
    conv_a = client.post("/v1/conversations", headers=headers, json={"title": "Conv A"}).json()["id"]
    conv_b = client.post("/v1/conversations", headers=headers, json={"title": "Conv B"}).json()["id"]

    # Non-existent ID
    fake_id = str(uuid.uuid4())
    bad_resp1 = client.post(
        f"/v1/conversations/{conv_a}/messages",
        headers=headers,
        json={"content": "Retry non-existent", "retry_message_id": fake_id},
    )
    assert bad_resp1.status_code == 404
    assert bad_resp1.json()["error"]["code"] == "RETRY_MESSAGE_NOT_FOUND"

    # Completed message in conv_a
    ok_resp = client.post(f"/v1/conversations/{conv_a}/messages", headers=headers, json={"content": "Normal msg"})
    assert ok_resp.status_code == 200
    comp_user_id = ok_resp.json()["user_message"]["id"]

    # Retrying an already completed message -> 409
    bad_resp2 = client.post(
        f"/v1/conversations/{conv_a}/messages",
        headers=headers,
        json={"content": "Retry completed", "retry_message_id": comp_user_id},
    )
    assert bad_resp2.status_code == 409
    assert bad_resp2.json()["error"]["code"] == "MESSAGE_ALREADY_COMPLETED"

    # Create failed message in conv_a
    mock_provider.set_should_raise(LLMTimeoutError("Fail A"))
    fail_resp = client.post(f"/v1/conversations/{conv_a}/messages", headers=headers, json={"content": "Failed in A"})
    assert fail_resp.status_code == 502
    failed_a_id = fail_resp.json()["error"]["details"]["failed_message_id"]

    # Attempting to retry conv_a's failed message inside conv_b -> 404
    mock_provider.set_should_raise(None)
    cross_retry_resp = client.post(
        f"/v1/conversations/{conv_b}/messages",
        headers=headers,
        json={"content": "Cross retry", "retry_message_id": failed_a_id},
    )
    assert cross_retry_resp.status_code == 404
    assert cross_retry_resp.json()["error"]["code"] == "RETRY_MESSAGE_NOT_FOUND"


def test_idempotency_key_mismatch_and_cross_conversation_reuse(chat_client):
    """
    Proves:
    1. Header and body idempotency key mismatch -> 400 IDEMPOTENCY_KEY_MISMATCH
    2. Reusing an idempotency key across different conversations -> 409 IDEMPOTENCY_KEY_REUSED
    """
    client, mock_provider = chat_client

    email = f"mismatch_{uuid.uuid4().hex[:8]}@example.com"
    reg_resp = client.post(
        "/v1/auth/register",
        json={"email": email, "password": "Password123!", "full_name": "Key Owner", "business_name": "Key Shop"},
    )
    headers = {"X-CSRF-Token": reg_resp.json()["csrf_token"]}
    conv_1 = client.post("/v1/conversations", headers=headers, json={"title": "Conv 1"}).json()["id"]
    conv_2 = client.post("/v1/conversations", headers=headers, json={"title": "Conv 2"}).json()["id"]

    # 1. Header vs Body mismatch
    headers_with_mismatch = {**headers, "Idempotency-Key": "header-val-123"}
    mismatch_resp = client.post(
        f"/v1/conversations/{conv_1}/messages",
        headers=headers_with_mismatch,
        json={"content": "Mismatch query", "idempotency_key": "body-val-456"},
    )
    assert mismatch_resp.status_code == 400
    assert mismatch_resp.json()["error"]["code"] == "IDEMPOTENCY_KEY_MISMATCH"

    # 2. Valid send in conv_1 with shared key
    shared_key = f"scoped_{uuid.uuid4().hex}"
    ok_resp = client.post(
        f"/v1/conversations/{conv_1}/messages",
        headers=headers,
        json={"content": "Valid in conv 1", "idempotency_key": shared_key},
    )
    assert ok_resp.status_code == 200

    # 3. Attempt to use same shared_key in conv_2 -> 409
    reused_resp = client.post(
        f"/v1/conversations/{conv_2}/messages",
        headers=headers,
        json={"content": "Attempt in conv 2", "idempotency_key": shared_key},
    )
    assert reused_resp.status_code == 409
    assert reused_resp.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"

