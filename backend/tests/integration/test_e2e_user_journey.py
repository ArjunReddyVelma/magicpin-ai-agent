import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.main import app
from backend.app.core.dependencies import get_llm_provider
from backend.app.ai.mock_provider import MockLLMProvider
from backend.app.repositories.action_repository import ActionRepository


def test_complete_end_to_end_user_journey(client: TestClient, db_session: Session):
    """
    Final Integration Audit: Complete End-to-End User Journey.
    Verifies every screen and backend workflow across the product lifecycle:
    1. Register new merchant
    2. Session restoration and sign out
    3. Re-login and credential verification
    4. View and update merchant profile
    5. Context CRUD with optimistic version concurrency
    6. Conversations, messaging, provider error recovery with retry
    7. Suggested actions review and decision recording (no external side effects)
    8. Permanent account deletion with password verification
    """
    unique_id = uuid.uuid4().hex[:8]
    email = f"journey_{unique_id}@example.com"
    password = "ValidJourneyPassword123!"

    # 1. Register
    reg_res = client.post(
        "/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "full_name": "Journey Merchant",
            "business_name": "Journey Sweets & Treats",
            "category": "Food & Beverage",
            "location": "Indiranagar, Bangalore",
        },
    )
    assert reg_res.status_code == 201
    auth_data = reg_res.json()
    assert auth_data["user"]["email"] == email
    assert auth_data["merchant"]["business_name"] == "Journey Sweets & Treats"
    csrf = auth_data["csrf_token"]
    assert csrf is not None
    merchant_id = uuid.UUID(auth_data["merchant"]["id"])

    # 2. Session Restoration via /v1/auth/me
    me_res = client.get("/v1/auth/me")
    assert me_res.status_code == 200
    assert me_res.json()["user"]["email"] == email

    # 3. Sign Out
    logout_res = client.post("/v1/auth/logout", headers={"X-CSRF-Token": csrf})
    assert logout_res.status_code == 200

    # Verify session is invalidated
    me_after_logout = client.get("/v1/auth/me")
    assert me_after_logout.status_code == 401

    # 4. Re-Login
    login_res = client.post(
        "/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login_res.status_code == 200
    login_data = login_res.json()
    csrf = login_data["csrf_token"]

    # 5. View and Update Merchant Profile
    prof_get = client.get("/v1/merchant/profile")
    assert prof_get.status_code == 200
    assert prof_get.json()["business_name"] == "Journey Sweets & Treats"

    prof_patch = client.patch(
        "/v1/merchant/profile",
        json={
            "business_name": "Journey Sweets Flagship Store",
            "description": "Premium regional artisanal desserts.",
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert prof_patch.status_code == 200
    assert prof_patch.json()["business_name"] == "Journey Sweets Flagship Store"

    # 6. Context CRUD with Optimistic Concurrency
    # 6a. Create context item
    ctx_create = client.post(
        "/v1/context",
        json={
            "item_type": "policy",
            "title": "Return Policy",
            "content": "Perishable sweets cannot be returned once delivered.",
            "is_active": True,
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert ctx_create.status_code == 201
    ctx_data = ctx_create.json()
    ctx_id = ctx_data["id"]
    assert ctx_data["version"] == 1

    # 6b. Update context item with optimistic concurrency (If-Match: "1")
    ctx_patch = client.patch(
        f"/v1/context/{ctx_id}",
        json={"content": "Defective packaging items may be replaced within 2 hours."},
        headers={"X-CSRF-Token": csrf, "If-Match": '"1"'},
    )
    assert ctx_patch.status_code == 200
    assert ctx_patch.json()["version"] == 2

    # 6c. Verify conflict rejection on stale version (If-Match: "1" fails because current is 2)
    ctx_conflict = client.patch(
        f"/v1/context/{ctx_id}",
        json={"content": "Stale edit"},
        headers={"X-CSRF-Token": csrf, "If-Match": '"1"'},
    )
    assert ctx_conflict.status_code == 409
    assert ctx_conflict.json()["error"]["code"] == "STALE_VERSION_CONFLICT"

    # 6d. Filter context items
    ctx_list = client.get("/v1/context?item_type=policy&is_active=true")
    assert ctx_list.status_code == 200
    assert ctx_list.json()["total"] == 1

    # 7. Conversations & Chat with Provider Failure Recovery
    # 7a. Create conversation
    conv_create = client.post(
        "/v1/conversations",
        json={"title": "Customer Questions"},
        headers={"X-CSRF-Token": csrf},
    )
    assert conv_create.status_code == 201
    conv_id = conv_create.json()["id"]

    # 7b. Chat with LLM provider (mock provider)
    app.dependency_overrides[get_llm_provider] = lambda: MockLLMProvider(
        default_response="Our return policy covers defective packaging within 2 hours."
    )

    msg_send = client.post(
        f"/v1/conversations/{conv_id}/messages",
        json={"content": "Can I replace a damaged sweet box?", "idempotency_key": "idemp-turn-1"},
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "idemp-turn-1"},
    )
    assert msg_send.status_code == 200
    chat_resp = msg_send.json()
    assert chat_resp["user_message"]["status"] == "complete"
    assert chat_resp["assistant_message"]["status"] == "complete"
    assert "damaged" in chat_resp["assistant_message"]["content"].lower() or "policy" in chat_resp["assistant_message"]["content"].lower()

    # 7c. Simulate provider failure and verify recovery via retry_message_id
    class FailingProvider:
        def generate_response(self, system_prompt, messages):
            raise RuntimeError("Temporary Groq rate limit")

    app.dependency_overrides[get_llm_provider] = lambda: FailingProvider()

    fail_send = client.post(
        f"/v1/conversations/{conv_id}/messages",
        json={"content": "What are your delivery hours?"},
        headers={"X-CSRF-Token": csrf},
    )
    assert fail_send.status_code == 502
    fail_data = fail_send.json()
    assert fail_data["error"]["code"] == "LLM_PROVIDER_ERROR"
    failed_msg_id = fail_data["error"]["details"]["failed_message_id"]

    # Restore working provider and safely retry the failed turn
    app.dependency_overrides[get_llm_provider] = lambda: MockLLMProvider(
        default_response="We deliver between 9 AM and 10 PM daily."
    )

    retry_send = client.post(
        f"/v1/conversations/{conv_id}/messages",
        json={
            "content": "What are your delivery hours?",
            "retry_message_id": failed_msg_id,
            "idempotency_key": "retry-turn-1",
        },
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "retry-turn-1"},
    )
    assert retry_send.status_code == 200
    retry_resp = retry_send.json()
    assert retry_resp["user_message"]["id"] == failed_msg_id
    assert retry_resp["user_message"]["status"] == "complete"
    assert retry_resp["assistant_message"]["status"] == "complete"

    # Clean up LLM override
    del app.dependency_overrides[get_llm_provider]

    # 8. Suggested Actions: Review and Decision Recording (No External Actions)
    action_repo = ActionRepository(db_session)
    action = action_repo.create(
        merchant_id=merchant_id,
        action_type="reply_draft",
        title="Delivery Delay Reply Draft",
        description="Draft reply explaining traffic delay for customer.",
        conversation_id=uuid.UUID(conv_id),
    )

    # 8a. List pending actions
    act_list = client.get("/v1/actions?status=pending")
    assert act_list.status_code == 200
    assert act_list.json()["total"] == 1

    # 8b. Approve action decision
    act_approve = client.post(
        f"/v1/actions/{action.id}/approve",
        headers={"X-CSRF-Token": csrf},
    )
    assert act_approve.status_code == 200
    assert act_approve.json()["status"] == "approved"
    assert act_approve.json()["reviewed_at"] is not None

    # 8c. Verify state transition locks: cannot re-approve or dismiss already approved item
    act_reapprove = client.post(
        f"/v1/actions/{action.id}/approve",
        headers={"X-CSRF-Token": csrf},
    )
    assert act_reapprove.status_code == 409

    # 9. Account Deletion with Password Confirmation
    # 9a. Rejects wrong password
    del_wrong = client.request(
        "DELETE",
        "/v1/auth/account",
        json={"password": "IncorrectPassword"},
        headers={"X-CSRF-Token": csrf},
    )
    assert del_wrong.status_code == 401
    assert del_wrong.json()["error"]["code"] == "INVALID_PASSWORD"

    # 9b. Accepts correct password and deletes account
    del_ok = client.request(
        "DELETE",
        "/v1/auth/account",
        json={"password": password},
        headers={"X-CSRF-Token": csrf},
    )
    assert del_ok.status_code == 200
    assert del_ok.json()["status"] == "ok"

    # 9c. Verify user is purged and subsequent login fails
    re_login = client.post(
        "/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert re_login.status_code == 401
