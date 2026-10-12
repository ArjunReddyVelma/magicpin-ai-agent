import uuid
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from unittest.mock import MagicMock

from backend.app.main import app
from backend.app.core.config import settings
from backend.app.core.dependencies import get_llm_provider
from backend.app.core.security import login_rate_limiter, PostgreSQLLoginRateLimiter
from backend.app.ai.mock_provider import MockLLMProvider
from backend.app.ai.context_retriever import ContextRetriever
from backend.app.models.context_item import ContextItem
from backend.app.models.user import User
from backend.app.models.merchant_profile import MerchantProfile


def test_cross_merchant_chat_isolation(client: TestClient):
    """
    SECURITY TEST: Proves Tenant B cannot post messages to Tenant A's conversation.
    Must return HTTP 404 without leaking conversation existence.
    """
    mock_provider = MockLLMProvider()
    app.dependency_overrides[get_llm_provider] = lambda: mock_provider
    try:
        # Register Merchant A
        email_a = f"tenant_a_{uuid.uuid4().hex[:8]}@example.com"
        reg_a = client.post(
            "/v1/auth/register",
            json={"email": email_a, "password": "Password123!", "full_name": "Merchant A", "business_name": "Store A"},
        )
        assert reg_a.status_code == 201
        csrf_a = reg_a.json()["csrf_token"]
        conv_a_resp = client.post(
            "/v1/conversations",
            headers={"X-CSRF-Token": csrf_a},
            json={"title": "Store A Inquiries"},
        )
        conv_a_id = conv_a_resp.json()["id"]

        # Register Merchant B (switches session cookie)
        email_b = f"tenant_b_{uuid.uuid4().hex[:8]}@example.com"
        reg_b = client.post(
            "/v1/auth/register",
            json={"email": email_b, "password": "Password123!", "full_name": "Merchant B", "business_name": "Store B"},
        )
        assert reg_b.status_code == 201
        csrf_b = reg_b.json()["csrf_token"]

        # Tenant B attempts to send message to Tenant A's conversation
        hostile_resp = client.post(
            f"/v1/conversations/{conv_a_id}/messages",
            headers={"X-CSRF-Token": csrf_b},
            json={"content": "Hostile message from B"},
        )
        assert hostile_resp.status_code == 404
        assert hostile_resp.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"
    finally:
        app.dependency_overrides.pop(get_llm_provider, None)


def test_cross_merchant_context_prompt_isolation(db_session: Session):
    """
    SECURITY TEST: Proves ContextRetriever never leaks Tenant B's context items
    into Tenant A's prompt retrieval even when keywords match identically.
    """
    retriever = ContextRetriever()
    user_a = User(
        email=f"iso_a_{uuid.uuid4().hex[:8]}@example.com",
        full_name="Iso A",
        password_hash="mock_hash",
    )
    user_b = User(
        email=f"iso_b_{uuid.uuid4().hex[:8]}@example.com",
        full_name="Iso B",
        password_hash="mock_hash",
    )
    db_session.add_all([user_a, user_b])
    db_session.flush()

    merchant_a = MerchantProfile(
        user_id=user_a.id,
        business_name="Store A",
    )
    merchant_b = MerchantProfile(
        user_id=user_b.id,
        business_name="Store B",
    )
    db_session.add_all([merchant_a, merchant_b])
    db_session.flush()

    merchant_a_id = merchant_a.id
    merchant_b_id = merchant_b.id

    # Create matching items for both merchants
    item_a = ContextItem(
        id=uuid.uuid4(),
        merchant_id=merchant_a_id,
        item_type="policy",
        title="Refund Policy",
        content="Tenant A refund policy: No refunds after 2 days.",
        is_active=True,
        version=1,
    )
    item_b = ContextItem(
        id=uuid.uuid4(),
        merchant_id=merchant_b_id,
        item_type="policy",
        title="Refund Policy",
        content="Tenant B confidential secret: Full cash refunds anytime.",
        is_active=True,
        version=1,
    )
    db_session.add_all([item_a, item_b])
    db_session.commit()


    # Query for Merchant A
    results_a = retriever.retrieve_relevant_context(
        merchant_id=merchant_a_id,
        query="Tell me about the refund policy",
        db=db_session,
    )
    assert len(results_a) == 1
    assert results_a[0].merchant_id == merchant_a_id
    assert "Tenant A refund policy" in results_a[0].content
    assert "Tenant B confidential secret" not in results_a[0].content


def test_chat_unauthenticated_and_csrf_protection(client: TestClient):
    """
    SECURITY TEST: Proves /v1/conversations/{id}/messages rejects unauthenticated
    requests with HTTP 401 and missing CSRF headers with HTTP 403.
    """
    dummy_conv_id = uuid.uuid4()

    # Unauthenticated
    unauth_resp = client.post(
        f"/v1/conversations/{dummy_conv_id}/messages",
        json={"content": "Hello"},
    )
    assert unauth_resp.status_code == 401

    # Authenticate but omit CSRF header
    reg_resp = client.post(
        "/v1/auth/register",
        json={"email": f"sec_{uuid.uuid4().hex[:8]}@example.com", "password": "Password123!", "full_name": "Sec User", "business_name": "Sec Shop"},
    )
    assert reg_resp.status_code == 201

    no_csrf_resp = client.post(
        f"/v1/conversations/{dummy_conv_id}/messages",
        json={"content": "Hello without CSRF"},
    )
    assert no_csrf_resp.status_code == 403
    assert no_csrf_resp.json()["error"]["code"] == "CSRF_TOKEN_MISSING"


def test_production_rate_limiter_fail_safe():
    """
    SECURITY TEST: Proves that in production environment, rate limiter fails safely
    with HTTP 503 DEPENDENCY_UNAVAILABLE instead of silently falling back to in-memory state.
    """
    limiter = PostgreSQLLoginRateLimiter()

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(settings, "APP_ENV", "production")

        # Calling without DB in production raises 503
        with pytest.raises(HTTPException) as exc_info:
            limiter.is_rate_limited("127.0.0.1:test@example.com", db=None)
        assert exc_info.value.status_code == 503
        assert exc_info.value.detail["error"]["code"] == "DEPENDENCY_UNAVAILABLE"

        # Simulating DB query error in production raises 503
        failing_db = MagicMock(spec=Session)
        failing_db.scalar.side_effect = Exception("DB Connection Lost")

        with pytest.raises(HTTPException) as exc_info2:
            limiter.is_rate_limited("127.0.0.1:test@example.com", db=failing_db)
        assert exc_info2.value.status_code == 503
        assert exc_info2.value.detail["error"]["code"] == "DEPENDENCY_UNAVAILABLE"
