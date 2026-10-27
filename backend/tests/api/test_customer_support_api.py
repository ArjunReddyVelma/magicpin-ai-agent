import hashlib
import uuid
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.ai.provider import LLMProvider, LLMResponse, LLMTimeoutError
from backend.app.core.dependencies import get_llm_provider
from backend.app.core.security import hash_session_token, hash_password
from backend.app.core.support_rate_limiter import support_rate_limiter
from backend.app.main import app
from backend.app.models.customer_support import (
    CustomerSupportSession,
    CustomerSupportMessage,
)
from backend.app.models.merchant_profile import MerchantProfile
from backend.app.repositories.customer_support_repository import CustomerSupportRepository



class MockWorkingLLMProvider(LLMProvider):
    def __init__(self, reply: str = "Thank you for reaching out! We are open daily from 9 AM to 9 PM."):
        self.reply = reply

    def generate_response(
        self,
        system_prompt: str,
        messages: list,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> LLMResponse:
        return LLMResponse(content=self.reply, provider="mock", model="mock-model")


class MockFailingLLMProvider(LLMProvider):
    def generate_response(
        self,
        system_prompt: str,
        messages: list,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> LLMResponse:
        raise LLMTimeoutError("LLM Provider Timeout after 5.0 seconds")


def _register_merchant(client: TestClient, name: str = "Support Merchant"):
    email = f"merch_{uuid.uuid4().hex[:8]}@example.com"
    r = client.post(
        "/v1/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": name,
            "business_name": f"{name} Store",
        },
    )
    assert r.status_code == 201
    return r.json()


@pytest.fixture(autouse=True)
def override_llm_mock():
    mock_provider = MockWorkingLLMProvider()
    app.dependency_overrides[get_llm_provider] = lambda: mock_provider
    yield mock_provider
    app.dependency_overrides.pop(get_llm_provider, None)


# ---------------------------------------------------------------------------
# 1. Public merchant lookup allowlisted fields only
# ---------------------------------------------------------------------------
def test_public_merchant_lookup_allowlisted_fields_only(
    client: TestClient, test_merchant: MerchantProfile
):
    resp = client.get(f"/v1/public/support/merchants/{test_merchant.id}")
    assert resp.status_code == 200
    data = resp.json()

    assert data["merchant_id"] == str(test_merchant.id)
    assert data["business_name"] == test_merchant.business_name
    assert data["category"] == test_merchant.category
    assert data["location"] == test_merchant.location
    assert "description" in data

    # Verify sensitive/internal fields are NOT exposed
    assert "user_id" not in data
    assert "timezone" not in data
    assert "created_at" not in data
    assert "updated_at" not in data


# ---------------------------------------------------------------------------
# 2. Unknown merchant returns 404
# ---------------------------------------------------------------------------
def test_public_merchant_lookup_unknown_merchant(client: TestClient):
    random_id = uuid.uuid4()
    resp = client.get(f"/v1/public/support/merchants/{random_id}")
    assert resp.status_code == 404
    data = resp.json()
    assert data["error"]["code"] == "MERCHANT_NOT_FOUND"


# ---------------------------------------------------------------------------
# 3. Session creation returns plaintext token, stores only hash
# ---------------------------------------------------------------------------
def test_create_session_returns_token_and_hashes_in_db(
    client: TestClient, db_session: Session, test_merchant: MerchantProfile
):
    resp = client.post(
        "/v1/public/support/sessions",
        json={"merchant_id": str(test_merchant.id), "customer_name": "Alice Customer"},
    )
    assert resp.status_code == 201
    data = resp.json()

    session_id = uuid.UUID(data["session_id"])
    customer_token = data["customer_token"]
    assert len(customer_token) >= 32
    assert data["status"] == "active"
    assert "created_at" in data

    # Check database persistence
    db_session.expire_all()
    session_row = db_session.get(CustomerSupportSession, session_id)
    assert session_row is not None
    assert session_row.merchant_id == test_merchant.id
    assert session_row.customer_name == "Alice Customer"
    assert session_row.status == "active"

    # Verify SHA-256 hash match and raw token NOT stored
    expected_hash = hashlib.sha256(customer_token.encode()).hexdigest()
    assert session_row.customer_token_hash == expected_hash
    assert customer_token != session_row.customer_token_hash


# ---------------------------------------------------------------------------
# 4. Missing/incorrect token rejected
# ---------------------------------------------------------------------------
def test_missing_and_invalid_token_rejected(
    client: TestClient, test_merchant: MerchantProfile
):
    # Create session
    create_resp = client.post(
        "/v1/public/support/sessions",
        json={"merchant_id": str(test_merchant.id)},
    )
    assert create_resp.status_code == 201
    session_id = create_resp.json()["session_id"]

    # 4a. Message submission without token -> 401
    r_no_tok = client.post(
        f"/v1/public/support/sessions/{session_id}/messages",
        json={"content": "Hello there"},
    )
    assert r_no_tok.status_code == 401
    assert r_no_tok.json()["error"]["code"] == "CUSTOMER_TOKEN_REQUIRED"

    # 4b. Message submission with invalid token -> 403
    r_bad_tok = client.post(
        f"/v1/public/support/sessions/{session_id}/messages",
        json={"content": "Hello there"},
        headers={"X-Customer-Token": "invalid_wrong_token_value_here"},
    )
    assert r_bad_tok.status_code == 403
    assert r_bad_tok.json()["error"]["code"] == "INVALID_CUSTOMER_TOKEN"

    # 4c. History request without token -> 401
    r_hist_no_tok = client.get(f"/v1/public/support/sessions/{session_id}/messages")
    assert r_hist_no_tok.status_code == 401
    assert r_hist_no_tok.json()["error"]["code"] == "CUSTOMER_TOKEN_REQUIRED"

    # 4d. History request with invalid token -> 403
    r_hist_bad_tok = client.get(
        f"/v1/public/support/sessions/{session_id}/messages",
        headers={"X-Customer-Token": "invalid_token_for_history"},
    )
    assert r_hist_bad_tok.status_code == 403
    assert r_hist_bad_tok.json()["error"]["code"] == "INVALID_CUSTOMER_TOKEN"


# ---------------------------------------------------------------------------
# 5. Token cannot access another customer's session
# ---------------------------------------------------------------------------
def test_cross_session_token_rejected(
    client: TestClient, test_merchant: MerchantProfile
):
    # Session A
    s_a = client.post(
        "/v1/public/support/sessions",
        json={"merchant_id": str(test_merchant.id), "customer_name": "Customer A"},
    ).json()
    # Session B
    s_b = client.post(
        "/v1/public/support/sessions",
        json={"merchant_id": str(test_merchant.id), "customer_name": "Customer B"},
    ).json()

    # Use Token A against Session B
    r_msg = client.post(
        f"/v1/public/support/sessions/{s_b['session_id']}/messages",
        json={"content": "Malicious inquiry"},
        headers={"X-Customer-Token": s_a["customer_token"]},
    )
    assert r_msg.status_code == 403
    assert r_msg.json()["error"]["code"] == "INVALID_CUSTOMER_TOKEN"

    r_hist = client.get(
        f"/v1/public/support/sessions/{s_b['session_id']}/messages",
        headers={"X-Customer-Token": s_a["customer_token"]},
    )
    assert r_hist.status_code == 403
    assert r_hist.json()["error"]["code"] == "INVALID_CUSTOMER_TOKEN"


# ---------------------------------------------------------------------------
# 6. Closed sessions reject inquiries
# ---------------------------------------------------------------------------
def test_closed_session_rejects_inquiries(
    client: TestClient, db_session: Session, test_merchant: MerchantProfile
):
    s = client.post(
        "/v1/public/support/sessions",
        json={"merchant_id": str(test_merchant.id)},
    ).json()
    session_id = uuid.UUID(s["session_id"])

    # Close the session in the database
    db_session.expire_all()
    session_obj = db_session.get(CustomerSupportSession, session_id)
    session_obj.status = "closed"
    db_session.commit()

    # Attempt to post message
    r = client.post(
        f"/v1/public/support/sessions/{session_id}/messages",
        json={"content": "Can I still ask a question?"},
        headers={"X-Customer-Token": s["customer_token"]},
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "SESSION_CLOSED"


# ---------------------------------------------------------------------------
# 7. Empty and oversized inquiries rejected
# ---------------------------------------------------------------------------
def test_empty_and_oversized_inquiries_rejected(
    client: TestClient, test_merchant: MerchantProfile
):
    s = client.post(
        "/v1/public/support/sessions",
        json={"merchant_id": str(test_merchant.id)},
    ).json()
    token = s["customer_token"]
    session_id = s["session_id"]

    # Empty string
    r_empty = client.post(
        f"/v1/public/support/sessions/{session_id}/messages",
        json={"content": ""},
        headers={"X-Customer-Token": token},
    )
    assert r_empty.status_code == 422

    # Whitespace only
    r_ws = client.post(
        f"/v1/public/support/sessions/{session_id}/messages",
        json={"content": "     \n\t   "},
        headers={"X-Customer-Token": token},
    )
    assert r_ws.status_code == 422

    # Exceeds max length (2000 chars)
    r_large = client.post(
        f"/v1/public/support/sessions/{session_id}/messages",
        json={"content": "x" * 2001},
        headers={"X-Customer-Token": token},
    )
    assert r_large.status_code == 422


# ---------------------------------------------------------------------------
# 8. Inquiry persistence survives AI provider failure
# ---------------------------------------------------------------------------
def test_inquiry_persistence_survives_ai_provider_failure(
    client: TestClient, db_session: Session, test_merchant: MerchantProfile
):
    app.dependency_overrides[get_llm_provider] = lambda: MockFailingLLMProvider()

    s = client.post(
        "/v1/public/support/sessions",
        json={"merchant_id": str(test_merchant.id)},
    ).json()
    token = s["customer_token"]
    session_id = s["session_id"]

    resp = client.post(
        f"/v1/public/support/sessions/{session_id}/messages",
        json={"content": "Is parking available at the Indiranagar branch?"},
        headers={"X-Customer-Token": token},
    )
    assert resp.status_code == 201
    data = resp.json()
    msg_id = uuid.UUID(data["id"])
    assert data["status"] == "needs_review"
    assert data["customer_text"] == "Is parking available at the Indiranagar branch?"

    # Check database persistence
    db_session.expire_all()
    msg_obj = db_session.get(CustomerSupportMessage, msg_id)
    assert msg_obj is not None
    assert msg_obj.status == "needs_review"
    assert msg_obj.ai_status == "failed"
    assert "LLM Provider Timeout" in (msg_obj.ai_error or "")
    assert msg_obj.suggested_reply is None


# ---------------------------------------------------------------------------
# 9. AI failure leaves inquiry available for merchant review
# ---------------------------------------------------------------------------
def test_ai_failure_leaves_inquiry_in_merchant_inbox(
    client: TestClient, db_session: Session
):
    app.dependency_overrides[get_llm_provider] = lambda: MockFailingLLMProvider()

    auth = _register_merchant(client, "Review Store")
    merchant_id = auth["merchant"]["id"]

    # Customer creates session and submits message
    s = client.post(
        "/v1/public/support/sessions",
        json={"merchant_id": merchant_id, "customer_name": "Bob Inquirer"},
    ).json()
    submit_r = client.post(
        f"/v1/public/support/sessions/{s['session_id']}/messages",
        json={"content": "Do you offer gluten-free bread?"},
        headers={"X-Customer-Token": s["customer_token"]},
    )
    assert submit_r.status_code == 201

    # Merchant views inbox
    inbox_r = client.get("/v1/support/messages?status=needs_review")
    assert inbox_r.status_code == 200
    inbox_data = inbox_r.json()
    assert inbox_data["total"] >= 1
    found = next((m for m in inbox_data["items"] if m["customer_text"] == "Do you offer gluten-free bread?"), None)
    assert found is not None
    assert found["status"] == "needs_review"
    assert found["ai_status"] == "failed"
    assert found["customer_name"] == "Bob Inquirer"


# ---------------------------------------------------------------------------
# 10. Suggestions not exposed to customer before delivery
# ---------------------------------------------------------------------------
def test_suggestions_not_exposed_to_customer_before_delivery(
    client: TestClient, db_session: Session, test_merchant: MerchantProfile
):
    app.dependency_overrides[get_llm_provider] = lambda: MockWorkingLLMProvider(
        reply="Yes, we have freshly baked gluten-free bread daily."
    )

    s = client.post(
        "/v1/public/support/sessions",
        json={"merchant_id": str(test_merchant.id)},
    ).json()
    token = s["customer_token"]
    session_id = s["session_id"]

    # 1. Customer submits inquiry
    post_r = client.post(
        f"/v1/public/support/sessions/{session_id}/messages",
        json={"content": "Do you have gluten-free bread?"},
        headers={"X-Customer-Token": token},
    )
    assert post_r.status_code == 201
    post_data = post_r.json()
    assert "suggested_reply" not in post_data
    assert "ai_status" not in post_data
    assert "ai_error" not in post_data

    # 2. Customer gets history
    hist_r = client.get(
        f"/v1/public/support/sessions/{session_id}/messages",
        headers={"X-Customer-Token": token},
    )
    assert hist_r.status_code == 200
    hist_data = hist_r.json()
    assert len(hist_data["items"]) == 1
    item = hist_data["items"][0]

    assert item["status"] == "needs_review"
    assert item["reply"] is None
    assert "suggested_reply" not in item
    assert "ai_status" not in item
    assert "ai_error" not in item


# ---------------------------------------------------------------------------
# 11. History returns only approved/delivered replies
# ---------------------------------------------------------------------------
def test_history_returns_only_delivered_replies(
    client: TestClient, db_session: Session, test_merchant: MerchantProfile
):
    s = client.post(
        "/v1/public/support/sessions",
        json={"merchant_id": str(test_merchant.id)},
    ).json()
    token = s["customer_token"]
    session_id = uuid.UUID(s["session_id"])

    # Message 1: Pending review
    m1_r = client.post(
        f"/v1/public/support/sessions/{session_id}/messages",
        json={"content": "Inquiry 1 pending"},
        headers={"X-Customer-Token": token},
    ).json()
    m1_id = uuid.UUID(m1_r["id"])

    # Message 2: Delivered reply
    m2_r = client.post(
        f"/v1/public/support/sessions/{session_id}/messages",
        json={"content": "Inquiry 2 answered"},
        headers={"X-Customer-Token": token},
    ).json()
    m2_id = uuid.UUID(m2_r["id"])

    # Manually mark message 2 as delivered in DB
    db_session.expire_all()
    msg2 = db_session.get(CustomerSupportMessage, m2_id)
    msg2.approved_reply = "This is our official merchant delivered response."
    msg2.status = "delivered"
    msg2.delivered_at = datetime.now(timezone.utc)
    db_session.commit()

    # Customer fetches history
    hist_r = client.get(
        f"/v1/public/support/sessions/{session_id}/messages",
        headers={"X-Customer-Token": token},
    )
    assert hist_r.status_code == 200
    items = hist_r.json()["items"]
    assert len(items) == 2

    item_1 = next(i for i in items if i["id"] == str(m1_id))
    item_2 = next(i for i in items if i["id"] == str(m2_id))

    # Item 1 is in review -> reply is None
    assert item_1["status"] == "needs_review"
    assert item_1["reply"] is None

    # Item 2 is delivered -> reply is approved text
    assert item_2["status"] == "delivered"
    assert item_2["reply"] == "This is our official merchant delivered response."
    assert item_2["delivered_at"] is not None


# ---------------------------------------------------------------------------
# 12. Merchant A cannot list, edit, or access Merchant B's messages
# ---------------------------------------------------------------------------
def test_merchant_tenant_isolation(client: TestClient, db_session: Session):
    # Register Merchant A
    auth_a = _register_merchant(client, "Merchant Alpha")
    merch_a_id = auth_a["merchant"]["id"]
    csrf_a = auth_a["csrf_token"]

    # Submit inquiry for Merchant A
    s_a = client.post(
        "/v1/public/support/sessions",
        json={"merchant_id": merch_a_id},
    ).json()
    msg_a = client.post(
        f"/v1/public/support/sessions/{s_a['session_id']}/messages",
        json={"content": "Confidential message for Merchant Alpha"},
        headers={"X-Customer-Token": s_a["customer_token"]},
    ).json()
    msg_a_id = msg_a["id"]

    # Register Merchant B (switches client session cookie to Merchant B)
    auth_b = _register_merchant(client, "Merchant Bravo")
    merch_b_id = auth_b["merchant"]["id"]
    csrf_b = auth_b["csrf_token"]

    # Merchant B inbox must NOT contain Merchant A's message
    inbox_b = client.get("/v1/support/messages")
    assert inbox_b.status_code == 200
    b_msg_ids = [m["id"] for m in inbox_b.json()["items"]]
    assert msg_a_id not in b_msg_ids

    # Merchant B cannot edit Merchant A's message -> 404
    patch_r = client.patch(
        f"/v1/support/messages/{msg_a_id}",
        json={"suggested_reply": "Malicious takeover attempt"},
        headers={"X-CSRF-Token": csrf_b},
    )
    assert patch_r.status_code == 404
    assert patch_r.json()["error"]["code"] == "MESSAGE_NOT_FOUND"


# ---------------------------------------------------------------------------
# 13. Unauthenticated merchant requests rejected
# ---------------------------------------------------------------------------
def test_unauthenticated_merchant_endpoints_rejected(client: TestClient):
    # Clear cookies by creating a clean client or removing cookies
    client.cookies.clear()

    # GET messages -> 401
    r_list = client.get("/v1/support/messages")
    assert r_list.status_code == 401

    # PATCH message -> 401
    r_patch = client.patch(
        f"/v1/support/messages/{uuid.uuid4()}",
        json={"suggested_reply": "Unauthenticated edit"},
    )
    assert r_patch.status_code == 401


# ---------------------------------------------------------------------------
# 14. Merchant editing does not mark reply delivered
# ---------------------------------------------------------------------------
def test_merchant_editing_does_not_mark_delivered(
    client: TestClient, db_session: Session
):
    auth = _register_merchant(client, "Draft Editor Store")
    merchant_id = auth["merchant"]["id"]
    csrf = auth["csrf_token"]

    # Submit inquiry
    s = client.post(
        "/v1/public/support/sessions",
        json={"merchant_id": merchant_id},
    ).json()
    msg = client.post(
        f"/v1/public/support/sessions/{s['session_id']}/messages",
        json={"content": "Can I get a discount for a party order?"},
        headers={"X-Customer-Token": s["customer_token"]},
    ).json()
    msg_id = uuid.UUID(msg["id"])

    # Merchant edits draft reply
    new_draft = "Yes! For party orders over 20 guests, we offer a 15% discount."
    patch_r = client.patch(
        f"/v1/support/messages/{msg_id}",
        json={"suggested_reply": new_draft},
        headers={"X-CSRF-Token": csrf},
    )
    assert patch_r.status_code == 200
    data = patch_r.json()

    assert data["suggested_reply"] == new_draft
    # CRITICAL: Must NOT be delivered
    assert data["status"] == "needs_review"
    assert data["approved_reply"] is None
    assert data["delivered_at"] is None

    # Verify directly in database
    db_session.expire_all()
    msg_row = db_session.get(CustomerSupportMessage, msg_id)
    assert msg_row.suggested_reply == new_draft
    assert msg_row.status == "needs_review"
    assert msg_row.approved_reply is None
    assert msg_row.delivered_at is None


# ---------------------------------------------------------------------------
# 15. Rate limiting and input bounds enforced
# ---------------------------------------------------------------------------
def test_rate_limiting_enforced(
    client: TestClient, test_merchant: MerchantProfile
):
    support_rate_limiter.reset()
    orig_sess_limit = support_rate_limiter.session_create_limit
    orig_msg_limit = support_rate_limiter.message_session_limit

    try:
        support_rate_limiter.session_create_limit = 2
        support_rate_limiter.message_session_limit = 2

        # 15a. Session creation rate limit
        r1 = client.post(
            "/v1/public/support/sessions",
            json={"merchant_id": str(test_merchant.id)},
        )
        assert r1.status_code == 201
        session_data = r1.json()

        r2 = client.post(
            "/v1/public/support/sessions",
            json={"merchant_id": str(test_merchant.id)},
        )
        assert r2.status_code == 201

        # 3rd request exceeds limit of 2 -> 429
        r3 = client.post(
            "/v1/public/support/sessions",
            json={"merchant_id": str(test_merchant.id)},
        )
        assert r3.status_code == 429
        assert r3.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"

        # 15b. Message submission rate limit
        s_id = session_data["session_id"]
        s_tok = session_data["customer_token"]

        m1 = client.post(
            f"/v1/public/support/sessions/{s_id}/messages",
            json={"content": "First message"},
            headers={"X-Customer-Token": s_tok},
        )
        assert m1.status_code == 201

        m2 = client.post(
            f"/v1/public/support/sessions/{s_id}/messages",
            json={"content": "Second message"},
            headers={"X-Customer-Token": s_tok},
        )
        assert m2.status_code == 201

        # 3rd message exceeds session limit of 2 -> 429
        m3 = client.post(
            f"/v1/public/support/sessions/{s_id}/messages",
            json={"content": "Third message exceeding limit"},
            headers={"X-Customer-Token": s_tok},
        )
        assert m3.status_code == 429
        assert m3.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"

    finally:
        support_rate_limiter.session_create_limit = orig_sess_limit
        support_rate_limiter.message_session_limit = orig_msg_limit
        support_rate_limiter.reset()


# ---------------------------------------------------------------------------
# 16. Regression: WhatsApp and copilot continue to pass
# ---------------------------------------------------------------------------
def test_regression_whatsapp_and_health(client: TestClient):
    # Health check
    h = client.get("/v1/healthz")
    assert h.status_code == 200
    assert h.json()["status"] == "ok"

    # WhatsApp unauthenticated check
    wa = client.get("/v1/whatsapp/account")
    assert wa.status_code == 401


# ---------------------------------------------------------------------------
# Milestone 3 Delivery & Inbox Tests
# ---------------------------------------------------------------------------

def test_delivery_missing_auth_and_invalid_csrf(client: TestClient, db_session: Session):
    auth = _register_merchant(client, "Delivery Auth Store")
    merch_id = auth["merchant"]["id"]
    csrf = auth["csrf_token"]

    # Customer submits inquiry
    s = client.post("/v1/public/support/sessions", json={"merchant_id": merch_id}).json()
    msg = client.post(
        f"/v1/public/support/sessions/{s['session_id']}/messages",
        json={"content": "What is your refund policy?"},
        headers={"X-Customer-Token": s["customer_token"]},
    ).json()
    msg_id = msg["id"]

    # 1. Unauthenticated request (no session cookie) -> 401
    client.cookies.clear()
    r_unauth = client.post(
        f"/v1/support/messages/{msg_id}/deliver",
        json={"reply_text": "We offer refunds within 7 days."},
    )
    assert r_unauth.status_code == 401

    # 2. Re-login to get cookies
    login_r = client.post(
        "/v1/auth/login",
        json={"email": auth["user"]["email"], "password": "Password123!"},
    )
    assert login_r.status_code == 200

    # 3. Invalid CSRF -> 403
    r_bad_csrf = client.post(
        f"/v1/support/messages/{msg_id}/deliver",
        json={"reply_text": "We offer refunds within 7 days."},
        headers={"X-CSRF-Token": "invalid_csrf_token"},
    )
    assert r_bad_csrf.status_code == 403


def test_merchant_cannot_deliver_other_merchant_inquiry(client: TestClient):
    auth_a = _register_merchant(client, "Delivery Store A")
    merch_a_id = auth_a["merchant"]["id"]

    # Create inquiry for Merchant A
    s_a = client.post("/v1/public/support/sessions", json={"merchant_id": merch_a_id}).json()
    msg_a = client.post(
        f"/v1/public/support/sessions/{s_a['session_id']}/messages",
        json={"content": "Question for store A"},
        headers={"X-Customer-Token": s_a["customer_token"]},
    ).json()
    msg_a_id = msg_a["id"]

    # Register Merchant B (switches session)
    auth_b = _register_merchant(client, "Delivery Store B")
    csrf_b = auth_b["csrf_token"]

    # Merchant B attempts to deliver Merchant A's inquiry -> 404
    r_cross = client.post(
        f"/v1/support/messages/{msg_a_id}/deliver",
        json={"reply_text": "Attacker hijacked reply"},
        headers={"X-CSRF-Token": csrf_b},
    )
    assert r_cross.status_code == 404
    assert r_cross.json()["error"]["code"] == "MESSAGE_NOT_FOUND"


def test_successful_delivery_persists_approved_reply_and_timestamp(
    client: TestClient, db_session: Session
):
    auth = _register_merchant(client, "Deliver Timestamp Store")
    merch_id = auth["merchant"]["id"]
    csrf = auth["csrf_token"]

    s = client.post("/v1/public/support/sessions", json={"merchant_id": merch_id}).json()
    msg = client.post(
        f"/v1/public/support/sessions/{s['session_id']}/messages",
        json={"content": "Are pets allowed in the outdoor seating area?"},
        headers={"X-Customer-Token": s["customer_token"]},
    ).json()
    msg_id = uuid.UUID(msg["id"])

    # Deliver reply
    reply_content = "Yes! Well-behaved pets are welcome in our garden seating area."
    deliver_r = client.post(
        f"/v1/support/messages/{msg_id}/deliver",
        json={"reply_text": reply_content},
        headers={"X-CSRF-Token": csrf},
    )
    assert deliver_r.status_code == 200
    data = deliver_r.json()

    assert data["status"] == "delivered"
    assert data["approved_reply"] == reply_content
    assert data["delivered_at"] is not None
    assert data["reviewed_at"] is not None

    # Check database persistence
    db_session.expire_all()
    msg_obj = db_session.get(CustomerSupportMessage, msg_id)
    assert msg_obj is not None
    assert msg_obj.status == "delivered"
    assert msg_obj.approved_reply == reply_content
    assert msg_obj.delivered_at is not None


def test_deliver_uses_existing_draft_if_reply_text_omitted(
    client: TestClient, db_session: Session
):
    auth = _register_merchant(client, "Deliver Draft Fallback Store")
    merch_id = auth["merchant"]["id"]
    csrf = auth["csrf_token"]

    s = client.post("/v1/public/support/sessions", json={"merchant_id": merch_id}).json()
    msg = client.post(
        f"/v1/public/support/sessions/{s['session_id']}/messages",
        json={"content": "What time do you close tonight?"},
        headers={"X-Customer-Token": s["customer_token"]},
    ).json()
    msg_id = uuid.UUID(msg["id"])

    # Deliver with empty payload {} - should use server-persisted suggested_reply
    deliver_r = client.post(
        f"/v1/support/messages/{msg_id}/deliver",
        json={},
        headers={"X-CSRF-Token": csrf},
    )
    assert deliver_r.status_code == 200
    data = deliver_r.json()

    assert data["status"] == "delivered"
    assert data["approved_reply"] == "Thank you for reaching out! We are open daily from 9 AM to 9 PM."
    assert data["delivered_at"] is not None


def test_deliver_rejects_empty_reply_text_when_no_draft(
    client: TestClient, db_session: Session
):
    app.dependency_overrides[get_llm_provider] = lambda: MockFailingLLMProvider()

    auth = _register_merchant(client, "Deliver Empty Reject Store")
    merch_id = auth["merchant"]["id"]
    csrf = auth["csrf_token"]

    s = client.post("/v1/public/support/sessions", json={"merchant_id": merch_id}).json()
    msg = client.post(
        f"/v1/public/support/sessions/{s['session_id']}/messages",
        json={"content": "Can I book a table?"},
        headers={"X-Customer-Token": s["customer_token"]},
    ).json()
    msg_id = uuid.UUID(msg["id"])

    # AI failed so suggested_reply is None; deliver with empty body should be rejected
    deliver_r = client.post(
        f"/v1/support/messages/{msg_id}/deliver",
        json={},
        headers={"X-CSRF-Token": csrf},
    )
    assert deliver_r.status_code == 400
    assert deliver_r.json()["error"]["code"] == "REPLY_TEXT_REQUIRED"


def test_customer_history_exposes_reply_only_after_delivery(
    client: TestClient, db_session: Session
):
    auth = _register_merchant(client, "History Visibility Store")
    merch_id = auth["merchant"]["id"]
    csrf = auth["csrf_token"]

    s = client.post("/v1/public/support/sessions", json={"merchant_id": merch_id}).json()
    token = s["customer_token"]
    session_id = s["session_id"]

    msg = client.post(
        f"/v1/public/support/sessions/{session_id}/messages",
        json={"content": "Do you offer takeout?"},
        headers={"X-Customer-Token": token},
    ).json()
    msg_id = msg["id"]

    # 1. Before delivery: Customer sees reply = None
    h1 = client.get(
        f"/v1/public/support/sessions/{session_id}/messages",
        headers={"X-Customer-Token": token},
    ).json()
    assert len(h1["items"]) == 1
    assert h1["items"][0]["status"] == "needs_review"
    assert h1["items"][0]["reply"] is None

    # 2. Merchant delivers reply
    client.post(
        f"/v1/support/messages/{msg_id}/deliver",
        json={"reply_text": "Yes, takeout is available via our website or pickup."},
        headers={"X-CSRF-Token": csrf},
    )

    # 3. After delivery: Customer sees delivered reply
    h2 = client.get(
        f"/v1/public/support/sessions/{session_id}/messages",
        headers={"X-Customer-Token": token},
    ).json()
    assert len(h2["items"]) == 1
    assert h2["items"][0]["status"] == "delivered"
    assert h2["items"][0]["reply"] == "Yes, takeout is available via our website or pickup."
    assert h2["items"][0]["delivered_at"] is not None


def test_repeated_delivery_returns_409_and_does_not_overwrite(
    client: TestClient, db_session: Session
):
    auth = _register_merchant(client, "Repeated Delivery Store")
    merch_id = auth["merchant"]["id"]
    csrf = auth["csrf_token"]

    s = client.post("/v1/public/support/sessions", json={"merchant_id": merch_id}).json()
    msg = client.post(
        f"/v1/public/support/sessions/{s['session_id']}/messages",
        json={"content": "Are kids meals available?"},
        headers={"X-Customer-Token": s["customer_token"]},
    ).json()
    msg_id = msg["id"]

    # First delivery succeeds
    r1 = client.post(
        f"/v1/support/messages/{msg_id}/deliver",
        json={"reply_text": "Original approved delivery text."},
        headers={"X-CSRF-Token": csrf},
    )
    assert r1.status_code == 200

    # Second delivery attempt returns 409 Conflict
    r2 = client.post(
        f"/v1/support/messages/{msg_id}/deliver",
        json={"reply_text": "Conflicting attempt to overwrite."},
        headers={"X-CSRF-Token": csrf},
    )
    assert r2.status_code == 409
    assert r2.json()["error"]["code"] == "MESSAGE_ALREADY_DELIVERED"

    # Verify database still has original approved text
    db_session.expire_all()
    msg_obj = db_session.get(CustomerSupportMessage, uuid.UUID(msg_id))
    assert msg_obj.approved_reply == "Original approved delivery text."


def test_dismiss_and_invalid_state_transitions(
    client: TestClient, db_session: Session
):
    auth = _register_merchant(client, "State Transition Store")
    merch_id = auth["merchant"]["id"]
    csrf = auth["csrf_token"]

    s = client.post("/v1/public/support/sessions", json={"merchant_id": merch_id}).json()
    msg = client.post(
        f"/v1/public/support/sessions/{s['session_id']}/messages",
        json={"content": "Spam or irrelevant message."},
        headers={"X-Customer-Token": s["customer_token"]},
    ).json()
    msg_id = msg["id"]

    # 1. Dismiss message
    r_dismiss = client.post(
        f"/v1/support/messages/{msg_id}/dismiss",
        headers={"X-CSRF-Token": csrf},
    )
    assert r_dismiss.status_code == 200
    assert r_dismiss.json()["status"] == "dismissed"

    # 2. Attempt to deliver a dismissed message -> 409
    r_deliver = client.post(
        f"/v1/support/messages/{msg_id}/deliver",
        json={"reply_text": "Cannot deliver dismissed"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r_deliver.status_code == 409
    assert r_deliver.json()["error"]["code"] == "MESSAGE_DISMISSED"

    # 3. Attempt to dismiss again -> 409
    r_dismiss_again = client.post(
        f"/v1/support/messages/{msg_id}/dismiss",
        headers={"X-CSRF-Token": csrf},
    )
    assert r_dismiss_again.status_code == 409
    assert r_dismiss_again.json()["error"]["code"] == "MESSAGE_ALREADY_DISMISSED"


def test_closed_session_allows_history_read_while_blocking_new_inquiries(
    client: TestClient, db_session: Session, test_merchant: MerchantProfile
):
    s = client.post(
        "/v1/public/support/sessions",
        json={"merchant_id": str(test_merchant.id)},
    ).json()
    session_id = uuid.UUID(s["session_id"])
    token = s["customer_token"]

    # Submit 1 message while active
    m = client.post(
        f"/v1/public/support/sessions/{session_id}/messages",
        json={"content": "Question before closing session"},
        headers={"X-Customer-Token": token},
    ).json()

    # Close session
    db_session.expire_all()
    session_obj = db_session.get(CustomerSupportSession, session_id)
    session_obj.status = "closed"
    db_session.commit()

    # 1. New message submission is rejected -> 400
    r_submit = client.post(
        f"/v1/public/support/sessions/{session_id}/messages",
        json={"content": "Can I submit when closed?"},
        headers={"X-Customer-Token": token},
    )
    assert r_submit.status_code == 400
    assert r_submit.json()["error"]["code"] == "SESSION_CLOSED"

    # 2. Reading history is allowed -> 200 OK
    r_hist = client.get(
        f"/v1/public/support/sessions/{session_id}/messages",
        headers={"X-Customer-Token": token},
    )
    assert r_hist.status_code == 200
    data = r_hist.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["id"] == m["id"]


def test_concurrent_delivery_attempts_protection():
    from concurrent.futures import ThreadPoolExecutor
    from backend.tests.conftest import TestingSessionLocal
    from backend.app.services.customer_support_service import CustomerSupportService
    from backend.app.models.user import User
    from fastapi import HTTPException

    # Set up records using an independent committed PostgreSQL connection
    setup_db = TestingSessionLocal()
    try:
        user = User(
            full_name="Concurrent Merchant Owner",
            email=f"concurrent_{uuid.uuid4().hex[:8]}@example.com",
            password_hash=hash_password("ValidPassword123!"),
            is_active=True,
        )
        setup_db.add(user)
        setup_db.flush()

        merchant = MerchantProfile(
            user_id=user.id,
            business_name="Concurrent Cafe",
            category="Restaurant",
        )
        setup_db.add(merchant)
        setup_db.flush()

        repo = CustomerSupportRepository(setup_db)
        session = repo.create_session(
            merchant_id=merchant.id,
            customer_token_hash="dummy_hash_for_concurrency",
            customer_name="Concurrent Tester",
            commit=False,
        )
        setup_db.flush()

        msg = repo.create_message(
            session_id=session.id,
            merchant_id=merchant.id,
            customer_text="Concurrent delivery inquiry",
            suggested_reply="Initial proposal",
            commit=False,
        )
        setup_db.commit()

        user_id = user.id
        merchant_id = merchant.id
        msg_id = msg.id
    finally:
        setup_db.close()

    results = []

    def attempt_delivery(worker_id: int, reply: str):
        thread_db = TestingSessionLocal()
        service = CustomerSupportService(db=thread_db)
        try:
            res = service.deliver_merchant_reply(
                message_id=msg_id,
                merchant_id=merchant_id,
                reply_text=reply,
            )
            results.append(("success", worker_id, res.approved_reply))
        except HTTPException as exc:
            results.append(("conflict", worker_id, exc.status_code))
        finally:
            thread_db.close()

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(attempt_delivery, 1, "Thread 1 reply")
            f2 = executor.submit(attempt_delivery, 2, "Thread 2 reply")
            f1.result()
            f2.result()

        # Exactly one succeeded and one conflicted with 409
        successes = [r for r in results if r[0] == "success"]
        conflicts = [r for r in results if r[0] == "conflict"]

        assert len(successes) == 1, f"Expected 1 success, got {len(successes)}: {results}"
        assert len(conflicts) == 1, f"Expected 1 conflict, got {len(conflicts)}: {results}"
        assert conflicts[0][2] == 409

        # Verify winning reply in database
        check_db = TestingSessionLocal()
        try:
            final_msg = check_db.get(CustomerSupportMessage, msg_id)
            assert final_msg is not None
            assert final_msg.status == "delivered"
            assert final_msg.approved_reply in ("Thread 1 reply", "Thread 2 reply")
        finally:
            check_db.close()
    finally:
        # Cleanup committed records
        cleanup_db = TestingSessionLocal()
        try:
            db_user = cleanup_db.get(User, user_id)
            if db_user:
                cleanup_db.delete(db_user)
                cleanup_db.commit()
        finally:
            cleanup_db.close()


def test_delivery_database_failure_does_not_report_success(
    client: TestClient, db_session: Session, monkeypatch
):
    from sqlalchemy.exc import OperationalError
    from backend.app.services.customer_support_service import CustomerSupportService

    auth = _register_merchant(client, "DB Failure Deliver Store")
    merch_id = auth["merchant"]["id"]
    csrf = auth["csrf_token"]

    s = client.post("/v1/public/support/sessions", json={"merchant_id": merch_id}).json()
    msg = client.post(
        f"/v1/public/support/sessions/{s['session_id']}/messages",
        json={"content": "Will this fail gracefully?"},
        headers={"X-Customer-Token": s["customer_token"]},
    ).json()
    msg_id = msg["id"]

    # Monkeypatch deliver_merchant_reply to simulate unexpected DB failure on transition
    def mock_failing_deliver(self, message_id, merchant_id, reply_text=None):
        raise OperationalError("connection lost during commit", {}, None)

    monkeypatch.setattr(CustomerSupportService, "deliver_merchant_reply", mock_failing_deliver)

    # Deliver attempt with raise_server_exceptions=False should return structured 500
    with TestClient(app, raise_server_exceptions=False) as no_raise_client:
        no_raise_client.cookies.update(client.cookies)
        r = no_raise_client.post(
            f"/v1/support/messages/{msg_id}/deliver",
            json={"reply_text": "Failed commit reply"},
            headers={"X-CSRF-Token": csrf},
        )
        assert r.status_code == 500
        assert r.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"

    # Restore deliver and verify message remains needs_review in DB
    monkeypatch.undo()
    db_session.expire_all()
    msg_obj = db_session.get(CustomerSupportMessage, uuid.UUID(msg_id))
    assert msg_obj.status == "needs_review"
    assert msg_obj.approved_reply is None
