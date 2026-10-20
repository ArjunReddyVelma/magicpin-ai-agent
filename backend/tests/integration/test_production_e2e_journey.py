import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.main import app
from backend.app.core.dependencies import get_llm_provider
from backend.app.ai.mock_provider import MockLLMProvider


def test_production_multi_merchant_e2e_journey(db_session: Session):
    """
    Milestone 9 Phase D: Complete Multi-Merchant End-to-End Production Journey.

    Covers all 16 required steps across two isolated merchants:
    1.  Create or register two independent merchant accounts.
    2.  Authenticate both merchants and establish separate sessions.
    3.  Verify unauthenticated access to protected endpoints is denied.
    4.  Load and update each merchant profile.
    5.  Create and retrieve merchant context for both accounts.
    6.  Edit and delete context, confirming expected state changes.
    7.  Start conversations for each merchant.
    8.  Submit support questions through chat API using deterministic test provider.
    9.  Verify assistant messages and conversation history persist across subsequent requests.
    10. Verify one merchant cannot read or modify the other merchant's context, conversations, or messages.
    11. Trigger qualifying customer-support request and verify suggested action creation.
    12. Verify retry/repeated submission does not create unintended duplicate actions.
    13. Approve or dismiss an action and verify resulting state persists.
    14. Verify actions cannot be read or processed by another merchant.
    15. Log out and verify session invalidation and subsequent access denial.
    16. Verify important failure paths (validation error, conflict, CSRF missing/invalid, provider failure/retry).
    """
    # Create two separate client instances to maintain independent cookie jars
    client_a = TestClient(app)
    client_b = TestClient(app)
    unauth_client = TestClient(app)

    unique_a = uuid.uuid4().hex[:8]
    unique_b = uuid.uuid4().hex[:8]

    email_a = f"merchant_a_{unique_a}@example.com"
    email_b = f"merchant_b_{unique_b}@example.com"
    password_a = "SecureCoffeePassword123!"
    password_b = "SecureSpicePassword456!"

    # =========================================================================
    # Step 1: Create or register two independent merchant accounts
    # =========================================================================
    reg_a = client_a.post(
        "/v1/auth/register",
        json={
            "email": email_a,
            "password": password_a,
            "full_name": "Merchant A Owner",
            "business_name": "Artisan Coffee Roasters",
            "category": "Food & Beverage",
            "location": "Indiranagar, Bangalore",
        },
    )
    assert reg_a.status_code == 201, "Step 1: Merchant A registration failed"
    data_a = reg_a.json()
    assert data_a["user"]["email"] == email_a
    assert data_a["merchant"]["business_name"] == "Artisan Coffee Roasters"
    csrf_a = data_a["csrf_token"]
    assert csrf_a is not None
    merchant_a_id = uuid.UUID(data_a["merchant"]["id"])

    reg_b = client_b.post(
        "/v1/auth/register",
        json={
            "email": email_b,
            "password": password_b,
            "full_name": "Merchant B Owner",
            "business_name": "Heritage Spice Bazaar",
            "category": "Retail",
            "location": "Fort, Mumbai",
        },
    )
    assert reg_b.status_code == 201, "Step 1: Merchant B registration failed"
    data_b = reg_b.json()
    assert data_b["user"]["email"] == email_b
    assert data_b["merchant"]["business_name"] == "Heritage Spice Bazaar"
    csrf_b = data_b["csrf_token"]
    assert csrf_b is not None
    merchant_b_id = uuid.UUID(data_b["merchant"]["id"])

    assert merchant_a_id != merchant_b_id, "Step 1: Merchants must have distinct IDs"

    # =========================================================================
    # Step 2: Authenticate both merchants and establish separate sessions
    # =========================================================================
    me_a = client_a.get("/v1/auth/me")
    assert me_a.status_code == 200, "Step 2: Merchant A session check failed"
    assert me_a.json()["user"]["email"] == email_a

    me_b = client_b.get("/v1/auth/me")
    assert me_b.status_code == 200, "Step 2: Merchant B session check failed"
    assert me_b.json()["user"]["email"] == email_b

    # =========================================================================
    # Step 3: Verify unauthenticated access to protected endpoints is denied
    # =========================================================================
    assert unauth_client.get("/v1/auth/me").status_code == 401
    assert unauth_client.get("/v1/merchant/profile").status_code == 401
    assert unauth_client.get("/v1/context").status_code == 401
    assert unauth_client.get("/v1/conversations").status_code == 401
    assert unauth_client.get("/v1/actions").status_code == 401
    assert unauth_client.post("/v1/context", json={"title": "Test"}).status_code == 401

    # =========================================================================
    # Step 4: Load and update each merchant profile
    # =========================================================================
    prof_a_get = client_a.get("/v1/merchant/profile")
    assert prof_a_get.status_code == 200
    assert prof_a_get.json()["business_name"] == "Artisan Coffee Roasters"

    patch_a = client_a.patch(
        "/v1/merchant/profile",
        json={"description": "Specialty single-origin beans and cold brews.", "timezone": "Asia/Kolkata"},
        headers={"X-CSRF-Token": csrf_a},
    )
    assert patch_a.status_code == 200
    assert patch_a.json()["description"] == "Specialty single-origin beans and cold brews."

    patch_b = client_b.patch(
        "/v1/merchant/profile",
        json={"description": "Organic whole spices directly from Kerala farms.", "timezone": "Asia/Kolkata"},
        headers={"X-CSRF-Token": csrf_b},
    )
    assert patch_b.status_code == 200
    assert patch_b.json()["description"] == "Organic whole spices directly from Kerala farms."

    # Verify updates persisted independently
    assert client_a.get("/v1/merchant/profile").json()["description"] == "Specialty single-origin beans and cold brews."
    assert client_b.get("/v1/merchant/profile").json()["description"] == "Organic whole spices directly from Kerala farms."

    # =========================================================================
    # Step 5: Create and retrieve merchant context for both accounts
    # =========================================================================
    ctx_a_create = client_a.post(
        "/v1/context",
        json={
            "item_type": "policy",
            "title": "Coffee Bean Return Policy",
            "content": "Perishable roasted coffee beans cannot be returned once heat seal is opened.",
            "is_active": True,
        },
        headers={"X-CSRF-Token": csrf_a},
    )
    assert ctx_a_create.status_code == 201
    ctx_a_id = ctx_a_create.json()["id"]

    ctx_b_create = client_b.post(
        "/v1/context",
        json={
            "item_type": "faq",
            "title": "Spice Wholesale Minimums",
            "content": "Wholesale orders require a minimum order volume of 10 kilograms.",
            "is_active": True,
        },
        headers={"X-CSRF-Token": csrf_b},
    )
    assert ctx_b_create.status_code == 201
    ctx_b_id = ctx_b_create.json()["id"]

    # Retrieve context list for each merchant
    list_a = client_a.get("/v1/context")
    assert list_a.status_code == 200
    assert list_a.json()["total"] == 1
    assert list_a.json()["items"][0]["id"] == ctx_a_id

    list_b = client_b.get("/v1/context")
    assert list_b.status_code == 200
    assert list_b.json()["total"] == 1
    assert list_b.json()["items"][0]["id"] == ctx_b_id

    # =========================================================================
    # Step 6: Edit and delete context, confirming expected state changes
    # =========================================================================
    temp_ctx = client_a.post(
        "/v1/context",
        json={
            "item_type": "operating_info",
            "title": "Temporary Holiday Hours",
            "content": "Roastery opens from 10 AM to 4 PM on holidays.",
            "is_active": True,
        },
        headers={"X-CSRF-Token": csrf_a},
    )
    assert temp_ctx.status_code == 201
    temp_ctx_id = temp_ctx.json()["id"]
    assert temp_ctx.json()["version"] == 1

    # Edit with optimistic concurrency
    patch_ctx = client_a.patch(
        f"/v1/context/{temp_ctx_id}",
        json={"content": "Holiday hours updated: 9 AM to 3 PM."},
        headers={"X-CSRF-Token": csrf_a, "If-Match": '"1"'},
    )
    assert patch_ctx.status_code == 200
    assert patch_ctx.json()["version"] == 2

    # Delete temporary context
    del_ctx = client_a.delete(f"/v1/context/{temp_ctx_id}", headers={"X-CSRF-Token": csrf_a})
    assert del_ctx.status_code == 200
    assert client_a.get(f"/v1/context/{temp_ctx_id}").status_code == 404

    # Ensure original context item remains intact
    assert client_a.get(f"/v1/context/{ctx_a_id}").status_code == 200

    # =========================================================================
    # Step 7: Start conversations for each merchant
    # =========================================================================
    conv_a = client_a.post(
        "/v1/conversations",
        json={"title": "Coffee Support - Batch 101"},
        headers={"X-CSRF-Token": csrf_a},
    )
    assert conv_a.status_code == 201
    conv_a_id = conv_a.json()["id"]

    conv_b = client_b.post(
        "/v1/conversations",
        json={"title": "Wholesale Questions"},
        headers={"X-CSRF-Token": csrf_b},
    )
    assert conv_b.status_code == 201
    conv_b_id = conv_b.json()["id"]

    assert conv_a_id != conv_b_id

    # =========================================================================
    # Step 8: Submit support questions through chat API using mock provider
    # =========================================================================
    app.dependency_overrides[get_llm_provider] = lambda: MockLLMProvider(
        default_response="Per our policy, opened coffee beans cannot be returned once heat seal is broken."
    )

    msg_a = client_a.post(
        f"/v1/conversations/{conv_a_id}/messages",
        json={"content": "Can a customer return an opened coffee bag?", "idempotency_key": f"turn_a_{unique_a}"},
        headers={"X-CSRF-Token": csrf_a, "Idempotency-Key": f"turn_a_{unique_a}"},
    )
    assert msg_a.status_code == 200
    chat_a = msg_a.json()
    assert chat_a["user_message"]["status"] == "complete"
    assert chat_a["assistant_message"]["status"] == "complete"
    assert len(chat_a["context_used"]) >= 1
    assert chat_a["context_used"][0]["context_id"] == ctx_a_id

    # =========================================================================
    # Step 9: Verify assistant messages and conversation history persist across subsequent requests
    # =========================================================================
    hist_a = client_a.get(f"/v1/conversations/{conv_a_id}/messages")
    assert hist_a.status_code == 200
    messages_a = hist_a.json()["items"]
    assert len(messages_a) >= 2
    assert messages_a[0]["role"] == "user"
    assert messages_a[1]["role"] == "assistant"

    # =========================================================================
    # Step 10: Verify tenant isolation: Merchant A cannot read/modify Merchant B's data
    # =========================================================================
    # Merchant A trying to read/write Merchant B context
    assert client_a.get(f"/v1/context/{ctx_b_id}").status_code == 404
    assert (
        client_a.patch(
            f"/v1/context/{ctx_b_id}",
            json={"content": "hacked"},
            headers={"X-CSRF-Token": csrf_a, "If-Match": '"1"'},
        ).status_code
        == 404
    )
    assert client_a.delete(f"/v1/context/{ctx_b_id}", headers={"X-CSRF-Token": csrf_a}).status_code == 404

    # Merchant A trying to read/write Merchant B conversations
    assert client_a.get(f"/v1/conversations/{conv_b_id}").status_code == 404
    assert client_a.get(f"/v1/conversations/{conv_b_id}/messages").status_code == 404
    assert client_a.post(
        f"/v1/conversations/{conv_b_id}/messages",
        json={"content": "Injected turn"},
        headers={"X-CSRF-Token": csrf_a},
    ).status_code == 404

    # Merchant B trying to read Merchant A data
    assert client_b.get(f"/v1/context/{ctx_a_id}").status_code == 404
    assert client_b.get(f"/v1/conversations/{conv_a_id}").status_code == 404

    # =========================================================================
    # Step 11: Trigger qualifying customer-support request & verify suggested action creation
    # =========================================================================
    app.dependency_overrides[get_llm_provider] = lambda: MockLLMProvider(
        default_response="Dear customer, I apologize for the delay. We are tracking your order with our delivery partner right now."
    )

    draft_turn = client_a.post(
        f"/v1/conversations/{conv_a_id}/messages",
        json={
            "content": "Please draft a reply to a customer complaining that their order delivery is delayed.",
            "idempotency_key": f"draft_key_{unique_a}",
        },
        headers={"X-CSRF-Token": csrf_a, "Idempotency-Key": f"draft_key_{unique_a}"},
    )
    assert draft_turn.status_code == 200

    # Verify suggested action was created for Merchant A
    actions_a = client_a.get("/v1/actions?status=pending")
    assert actions_a.status_code == 200
    assert actions_a.json()["total"] == 1
    action_a = actions_a.json()["items"][0]
    action_a_id = action_a["id"]
    assert action_a["action_type"] == "reply_draft"
    assert action_a["status"] == "pending"

    # =========================================================================
    # Step 12: Verify retry / repeated submission does not create duplicate actions
    # =========================================================================
    duplicate_turn = client_a.post(
        f"/v1/conversations/{conv_a_id}/messages",
        json={
            "content": "Please draft a reply to a customer complaining that their order delivery is delayed.",
            "idempotency_key": f"draft_key_{unique_a}",
        },
        headers={"X-CSRF-Token": csrf_a, "Idempotency-Key": f"draft_key_{unique_a}"},
    )
    assert duplicate_turn.status_code == 200
    # Actions count must still be exactly 1
    actions_a_recheck = client_a.get("/v1/actions?status=pending")
    assert actions_a_recheck.json()["total"] == 1

    # =========================================================================
    # Step 13: Approve or dismiss an action and verify resulting state persists
    # =========================================================================
    approve_res = client_a.post(f"/v1/actions/{action_a_id}/approve", headers={"X-CSRF-Token": csrf_a})
    assert approve_res.status_code == 200
    assert approve_res.json()["status"] == "approved"
    assert approve_res.json()["reviewed_at"] is not None

    # Cannot re-approve or dismiss an already-reviewed action
    assert client_a.post(f"/v1/actions/{action_a_id}/approve", headers={"X-CSRF-Token": csrf_a}).status_code == 409
    assert client_a.post(f"/v1/actions/{action_a_id}/dismiss", headers={"X-CSRF-Token": csrf_a}).status_code == 409

    # Verify persisted review state
    get_action_a = client_a.get(f"/v1/actions/{action_a_id}")
    assert get_action_a.status_code == 200
    assert get_action_a.json()["status"] == "approved"

    # =========================================================================
    # Step 14: Verify actions cannot be read or processed by another merchant
    # =========================================================================
    assert client_b.get("/v1/actions").json()["total"] == 0
    assert client_b.get(f"/v1/actions/{action_a_id}").status_code == 404
    assert client_b.post(f"/v1/actions/{action_a_id}/approve", headers={"X-CSRF-Token": csrf_b}).status_code == 404
    assert client_b.post(f"/v1/actions/{action_a_id}/dismiss", headers={"X-CSRF-Token": csrf_b}).status_code == 404

    # =========================================================================
    # Step 15: Log out and verify session invalidation and subsequent access denial
    # =========================================================================
    logout_a = client_a.post("/v1/auth/logout", headers={"X-CSRF-Token": csrf_a})
    assert logout_a.status_code == 200
    assert client_a.get("/v1/auth/me").status_code == 401
    assert client_a.get("/v1/merchant/profile").status_code == 401

    # Merchant B's session remains active
    assert client_b.get("/v1/auth/me").status_code == 200

    logout_b = client_b.post("/v1/auth/logout", headers={"X-CSRF-Token": csrf_b})
    assert logout_b.status_code == 200
    assert client_b.get("/v1/auth/me").status_code == 401

    # Re-login Merchant A for failure path testing
    login_a = client_a.post("/v1/auth/login", json={"email": email_a, "password": password_a})
    assert login_a.status_code == 200
    csrf_a = login_a.json()["csrf_token"]

    # =========================================================================
    # Step 16: Verify important failure paths (validation, conflicts, CSRF, AI retry)
    # =========================================================================
    # 16a: Invalid input on registration
    bad_reg = client_a.post("/v1/auth/register", json={"email": "bad", "password": "short"})
    assert bad_reg.status_code == 422
    assert bad_reg.json()["error"]["code"] == "VALIDATION_ERROR"

    # 16b: Duplicate email registration conflict
    dup_reg = client_a.post(
        "/v1/auth/register",
        json={
            "email": email_a,
            "password": password_a,
            "full_name": "Duplicate",
            "business_name": "Duplicate",
        },
    )
    assert dup_reg.status_code == 409
    assert dup_reg.json()["error"]["code"] == "EMAIL_ALREADY_EXISTS"

    # 16c: Missing CSRF token on state-changing request
    no_csrf = client_a.patch("/v1/merchant/profile", json={"business_name": "No CSRF"})
    assert no_csrf.status_code == 403
    assert no_csrf.json()["error"]["code"] == "CSRF_TOKEN_MISSING"

    # 16d: Invalid CSRF token
    bad_csrf = client_a.patch(
        "/v1/merchant/profile",
        json={"business_name": "Bad CSRF"},
        headers={"X-CSRF-Token": "invalid-token-string"},
    )
    assert bad_csrf.status_code == 403
    assert bad_csrf.json()["error"]["code"] == "CSRF_TOKEN_INVALID"

    # 16e: Stale version conflict on context
    stale_patch = client_a.patch(
        f"/v1/context/{ctx_a_id}",
        json={"content": "Stale update"},
        headers={"X-CSRF-Token": csrf_a, "If-Match": '"999"'},
    )
    assert stale_patch.status_code == 409
    assert stale_patch.json()["error"]["code"] == "STALE_VERSION_CONFLICT"

    # 16f: AI Provider failure recovery via retry_message_id
    class TemporaryFailingProvider:
        def generate_response(self, system_prompt, messages):
            raise RuntimeError("Upstream AI Provider Rate Limit 429")

    app.dependency_overrides[get_llm_provider] = lambda: TemporaryFailingProvider()

    failed_turn = client_a.post(
        f"/v1/conversations/{conv_a_id}/messages",
        json={"content": "What are your holiday specials?"},
        headers={"X-CSRF-Token": csrf_a},
    )
    assert failed_turn.status_code == 502
    assert failed_turn.json()["error"]["code"] == "LLM_PROVIDER_ERROR"
    failed_message_id = failed_turn.json()["error"]["details"]["failed_message_id"]

    # Restore healthy provider and retry failed message
    app.dependency_overrides[get_llm_provider] = lambda: MockLLMProvider(
        default_response="Our holiday special is a dark roast peppermint blend."
    )

    retry_turn = client_a.post(
        f"/v1/conversations/{conv_a_id}/messages",
        json={
            "content": "What are your holiday specials?",
            "retry_message_id": failed_message_id,
            "idempotency_key": f"retry_turn_{unique_a}",
        },
        headers={"X-CSRF-Token": csrf_a, "Idempotency-Key": f"retry_turn_{unique_a}"},
    )
    assert retry_turn.status_code == 200
    assert retry_turn.json()["user_message"]["id"] == failed_message_id
    assert retry_turn.json()["user_message"]["status"] == "complete"
    assert retry_turn.json()["assistant_message"]["status"] == "complete"

    # Clean up dependency overrides
    app.dependency_overrides.clear()
