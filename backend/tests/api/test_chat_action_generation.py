import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy import select

from backend.app.main import app
from backend.app.core.dependencies import get_llm_provider
from backend.app.ai.mock_provider import MockLLMProvider
from backend.app.ai.provider import LLMTimeoutError
from backend.app.models.suggested_action import SuggestedAction


@pytest.fixture
def chat_action_client(client: TestClient):
    mock_provider = MockLLMProvider(
        default_response="Dear customer, we sincerely apologize for the delay in your food order. It will arrive shortly."
    )
    app.dependency_overrides[get_llm_provider] = lambda: mock_provider
    yield client, mock_provider
    app.dependency_overrides.pop(get_llm_provider, None)


def _register_merchant(client: TestClient, name: str = "Support Merchant"):
    email = f"action_{uuid.uuid4().hex[:8]}@example.com"
    reg_resp = client.post(
        "/v1/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": name,
            "business_name": f"{name} Store",
            "category": "Restaurant",
        },
    )
    assert reg_resp.status_code == 201
    csrf_token = reg_resp.json()["csrf_token"]
    merchant_id = reg_resp.json()["merchant"]["id"]
    return {"csrf_token": csrf_token, "merchant_id": merchant_id, "email": email}


def test_eligible_customer_support_turn_creates_suggested_action(chat_action_client, db_session: Session):
    client, mock_provider = chat_action_client
    auth = _register_merchant(client, "Royal Biryani")
    headers = {"X-CSRF-Token": auth["csrf_token"]}

    # 1. Create a conversation
    conv_resp = client.post("/v1/conversations", headers=headers, json={"title": "Delayed Delivery Issue"})
    assert conv_resp.status_code == 201
    conv_id = conv_resp.json()["id"]

    # 2. Send eligible customer-support drafting request
    chat_resp = client.post(
        f"/v1/conversations/{conv_id}/messages",
        headers=headers,
        json={
            "content": "A customer is complaining their order is 40 minutes late. Draft a reply using our store policy.",
            "idempotency_key": "turn-draft-1",
        },
    )
    assert chat_resp.status_code == 200
    data = chat_resp.json()
    user_msg_id = data["user_message"]["id"]
    assistant_content = data["assistant_message"]["content"]

    # 3. Query suggested actions via API
    actions_resp = client.get("/v1/actions?status=pending")
    assert actions_resp.status_code == 200
    actions_data = actions_resp.json()
    assert actions_data["total"] == 1
    assert len(actions_data["items"]) == 1

    action = actions_data["items"][0]
    assert action["action_type"] == "reply_draft"
    assert action["status"] == "pending"
    assert action["created_by"] == "assistant"
    assert action["conversation_id"] == conv_id
    assert action["merchant_id"] == auth["merchant_id"]
    assert "Customer Reply:" in action["title"]
    assert action["description"] == assistant_content
    assert action["payload"]["generated_reply"] == assistant_content
    assert action["payload"]["user_message_id"] == user_msg_id
    assert action["payload"]["conversation_id"] == conv_id


def test_damaged_product_support_request_creates_reply_draft(chat_action_client):
    client, mock_provider = chat_action_client
    auth = _register_merchant(client, "Damaged Product Merchant")
    headers = {"X-CSRF-Token": auth["csrf_token"]}

    conv_resp = client.post("/v1/conversations", headers=headers, json={"title": "Damaged Product Issue"})
    assert conv_resp.status_code == 201
    conv_id = conv_resp.json()["id"]

    chat_resp = client.post(
        f"/v1/conversations/{conv_id}/messages",
        headers=headers,
        json={"content": "A customer received a damaged product. What should we tell them?"},
    )
    assert chat_resp.status_code == 200

    actions_resp = client.get("/v1/actions?status=pending", headers=headers)
    assert actions_resp.status_code == 200
    data = actions_resp.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    action = data["items"][0]
    assert action["action_type"] == "reply_draft"
    assert action["status"] == "pending"
    assert action["merchant_id"] == auth["merchant_id"]
    assert action["conversation_id"] == conv_id


def test_cold_food_colloquial_request_creates_reply_draft(chat_action_client):
    client, mock_provider = chat_action_client
    auth = _register_merchant(client, "Cold Food Merchant")
    headers = {"X-CSRF-Token": auth["csrf_token"]}

    conv_resp = client.post("/v1/conversations", headers=headers, json={"title": "Cold Food Complaint"})
    assert conv_resp.status_code == 201
    conv_id = conv_resp.json()["id"]

    chat_resp = client.post(
        f"/v1/conversations/{conv_id}/messages",
        headers=headers,
        json={"content": "A customer's food was cold; write a message to them."},
    )
    assert chat_resp.status_code == 200

    actions_resp = client.get("/v1/actions?status=pending", headers=headers)
    assert actions_resp.status_code == 200
    data = actions_resp.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    action = data["items"][0]
    assert action["action_type"] == "reply_draft"
    assert action["status"] == "pending"
    assert action["merchant_id"] == auth["merchant_id"]
    assert action["conversation_id"] == conv_id


def test_non_actionable_message_does_not_create_action(chat_action_client):
    client, mock_provider = chat_action_client
    auth = _register_merchant(client, "General Merchant")
    headers = {"X-CSRF-Token": auth["csrf_token"]}

    conv_resp = client.post("/v1/conversations", headers=headers, json={"title": "General Q&A"})
    conv_id = conv_resp.json()["id"]

    # Send general greeting / non-actionable questions, including informational queries
    queries = [
        "Hello! How are you doing today?",
        "What are my store operating hours?",
        "What are our delivery hours?",
        "Explain how the dashboard works.",
    ]
    for q in queries:
        resp = client.post(
            f"/v1/conversations/{conv_id}/messages",
            headers=headers,
            json={"content": q},
        )
        assert resp.status_code == 200

    # Review queue should remain completely empty (0 items)
    actions_resp = client.get("/v1/actions", headers=headers)
    assert actions_resp.status_code == 200
    assert actions_resp.json()["total"] == 0
    assert len(actions_resp.json()["items"]) == 0


def test_failed_ai_call_creates_no_action(chat_action_client, db_session: Session):
    client, mock_provider = chat_action_client
    auth = _register_merchant(client, "Timeout Merchant")
    headers = {"X-CSRF-Token": auth["csrf_token"]}

    conv_resp = client.post("/v1/conversations", headers=headers, json={"title": "Failing Conv"})
    conv_id = conv_resp.json()["id"]

    # Configure provider to raise timeout
    mock_provider.set_should_raise(LLMTimeoutError("Simulated LLM gateway timeout"))

    fail_resp = client.post(
        f"/v1/conversations/{conv_id}/messages",
        headers=headers,
        json={"content": "Customer order is delayed. Draft a response."},
    )
    assert fail_resp.status_code == 502

    # Verify 0 actions in DB and in API
    actions_resp = client.get("/v1/actions")
    assert actions_resp.status_code == 200
    assert actions_resp.json()["total"] == 0


def test_replaying_idempotent_request_does_not_create_duplicate_action(chat_action_client):
    client, mock_provider = chat_action_client
    auth = _register_merchant(client, "Idempotent Merchant")
    headers = {"X-CSRF-Token": auth["csrf_token"]}

    conv_resp = client.post("/v1/conversations", headers=headers, json={"title": "Idempotent Conv"})
    conv_id = conv_resp.json()["id"]

    idem_key = "support-turn-exact-idem-1"
    payload = {
        "content": "A customer is complaining their delivery is delayed. Draft a polite reply.",
        "idempotency_key": idem_key,
    }

    # Initial send
    resp1 = client.post(f"/v1/conversations/{conv_id}/messages", headers=headers, json=payload)
    assert resp1.status_code == 200

    # Exactly 1 action created
    act1 = client.get("/v1/actions")
    assert act1.json()["total"] == 1
    action_id = act1.json()["items"][0]["id"]

    # Replay identical idempotent request
    resp2 = client.post(f"/v1/conversations/{conv_id}/messages", headers=headers, json=payload)
    assert resp2.status_code == 200

    # Still exactly 1 action (no duplicate!)
    act2 = client.get("/v1/actions")
    assert act2.json()["total"] == 1
    assert act2.json()["items"][0]["id"] == action_id


def test_tenant_isolation_prevents_cross_merchant_action_access(chat_action_client):
    client, mock_provider = chat_action_client

    # Merchant A
    auth_a = _register_merchant(client, "Merchant Alpha")
    headers_a = {"X-CSRF-Token": auth_a["csrf_token"]}
    conv_a = client.post("/v1/conversations", headers=headers_a, json={"title": "Alpha Support"}).json()["id"]
    client.post(
        f"/v1/conversations/{conv_a}/messages",
        headers=headers_a,
        json={"content": "Customer wants a refund for damaged goods. Draft a reply."},
    )
    actions_a = client.get("/v1/actions", headers=headers_a).json()
    assert actions_a["total"] == 1
    action_a_id = actions_a["items"][0]["id"]

    # Merchant B
    auth_b = _register_merchant(client, "Merchant Beta")
    headers_b = {"X-CSRF-Token": auth_b["csrf_token"]}

    # Merchant B listing actions sees 0 items
    actions_b = client.get("/v1/actions", headers=headers_b).json()
    assert actions_b["total"] == 0

    # Merchant B attempting to get Merchant A's action gets 404
    get_cross = client.get(f"/v1/actions/{action_a_id}", headers=headers_b)
    assert get_cross.status_code == 404

    # Merchant B attempting to approve Merchant A's action gets 404
    approve_cross = client.post(f"/v1/actions/{action_a_id}/approve", headers=headers_b)
    assert approve_cross.status_code == 404


def test_approval_and_dismissal_update_state_without_external_side_effects(chat_action_client):
    client, mock_provider = chat_action_client
    auth = _register_merchant(client, "Decision Merchant")
    headers = {"X-CSRF-Token": auth["csrf_token"]}

    conv_id = client.post("/v1/conversations", headers=headers, json={"title": "Order Review"}).json()["id"]

    # Create action 1
    client.post(
        f"/v1/conversations/{conv_id}/messages",
        headers=headers,
        json={"content": "Customer inquiry: Where is my order? Draft a polite reply."},
    )
    # Create action 2
    client.post(
        f"/v1/conversations/{conv_id}/messages",
        headers=headers,
        json={"content": "Customer complaint: Food was cold. Draft a response."},
    )

    actions = client.get("/v1/actions?status=pending").json()["items"]
    assert len(actions) == 2
    act_approve_id = actions[0]["id"]
    act_dismiss_id = actions[1]["id"]

    # 1. Approve action 1
    res_app = client.post(f"/v1/actions/{act_approve_id}/approve", headers=headers)
    assert res_app.status_code == 200
    assert res_app.json()["status"] == "approved"
    assert res_app.json()["reviewed_at"] is not None

    # Cannot re-approve or dismiss an already approved action
    re_app = client.post(f"/v1/actions/{act_approve_id}/approve", headers=headers)
    assert re_app.status_code == 409
    re_dis = client.post(f"/v1/actions/{act_approve_id}/dismiss", headers=headers)
    assert re_dis.status_code == 409

    # 2. Dismiss action 2
    res_dis = client.post(f"/v1/actions/{act_dismiss_id}/dismiss", headers=headers)
    assert res_dis.status_code == 200
    assert res_dis.json()["status"] == "dismissed"
    assert res_dis.json()["reviewed_at"] is not None

    # Verify pending queue is now 0
    pending_now = client.get("/v1/actions?status=pending").json()
    assert pending_now["total"] == 0


def test_retrying_failed_message_creates_single_action_on_success(chat_action_client):
    client, mock_provider = chat_action_client
    auth = _register_merchant(client, "Retry Merchant")
    headers = {"X-CSRF-Token": auth["csrf_token"]}

    conv_id = client.post("/v1/conversations", headers=headers, json={"title": "Retry Support"}).json()["id"]

    # 1. Fail first attempt
    mock_provider.set_should_raise(LLMTimeoutError("Initial timeout"))
    fail_res = client.post(
        f"/v1/conversations/{conv_id}/messages",
        headers=headers,
        json={"content": "Customer wants to know where their late food order is. Draft a reply."},
    )
    assert fail_res.status_code == 502
    failed_id = fail_res.json()["error"]["details"]["failed_message_id"]

    # 0 actions exist when turn failed
    assert client.get("/v1/actions").json()["total"] == 0

    # 2. Recover provider and retry
    mock_provider.set_should_raise(None)
    retry_res = client.post(
        f"/v1/conversations/{conv_id}/messages",
        headers=headers,
        json={
            "content": "Customer wants to know where their late food order is. Draft a reply.",
            "retry_message_id": failed_id,
            "idempotency_key": "retry-action-key-1",
        },
    )
    assert retry_res.status_code == 200

    # 3. Exactly 1 pending action created now that retry succeeded
    actions = client.get("/v1/actions?status=pending").json()
    assert actions["total"] == 1
    assert actions["items"][0]["payload"]["user_message_id"] == failed_id

