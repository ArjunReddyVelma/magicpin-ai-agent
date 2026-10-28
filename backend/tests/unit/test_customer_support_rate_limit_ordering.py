import uuid
from unittest.mock import MagicMock
import pytest
from fastapi import HTTPException

from backend.app.api.v1.routes.public_support import submit_customer_inquiry
from backend.app.schemas.customer_support import CustomerInquiryRequest
from backend.app.models.customer_support import CustomerSupportSession, CustomerSupportMessage
from backend.app.core.support_rate_limiter import PublicSupportRateLimiter


def test_invalid_token_rejects_before_recording_quota(monkeypatch):
    """
    Unit test: Verifies that submit_customer_inquiry authenticates the customer token
    before calling support_rate_limiter.record_message_submission.
    If the customer token is missing or invalid, verify_customer_session raises an HTTPException (401/403)
    and record_message_submission is NEVER called, preventing session quota consumption.
    """
    mock_db = MagicMock()
    mock_request = MagicMock()
    mock_request.client.host = "192.168.1.100"
    mock_request.headers = {}

    mock_rate_limiter = MagicMock()
    monkeypatch.setattr(
        "backend.app.api.v1.routes.public_support.support_rate_limiter", mock_rate_limiter
    )

    mock_service = MagicMock()
    # Simulate verify_customer_session raising 403 on invalid token
    mock_service.verify_customer_session.side_effect = HTTPException(
        status_code=403, detail={"error": {"code": "INVALID_CUSTOMER_TOKEN", "message": "Invalid token"}}
    )
    monkeypatch.setattr(
        "backend.app.api.v1.routes.public_support.CustomerSupportService",
        lambda db, llm_provider=None: mock_service,
    )

    session_id = uuid.uuid4()
    req = CustomerInquiryRequest(content="Attempt with invalid token")

    with pytest.raises(HTTPException) as exc_info:
        submit_customer_inquiry(
            session_id=session_id,
            req=req,
            request=mock_request,
            x_customer_token="invalid_token_xyz",
            db=mock_db,
            llm_provider=MagicMock(),
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["error"]["code"] == "INVALID_CUSTOMER_TOKEN"

    # check_message_submission was checked upfront
    mock_rate_limiter.check_message_submission.assert_called_once()

    # CRITICAL: record_message_submission must NOT be called on invalid token!
    mock_rate_limiter.record_message_submission.assert_not_called()
    mock_service.submit_customer_inquiry.assert_not_called()


def test_valid_token_authenticates_then_records_and_submits(monkeypatch):
    """
    Unit test: Verifies that submit_customer_inquiry verifies the session, records quota,
    and then submits the inquiry when the customer token is valid.
    """
    mock_db = MagicMock()
    mock_request = MagicMock()
    mock_request.client.host = "192.168.1.100"
    mock_request.headers = {}

    call_order = []

    mock_rate_limiter = MagicMock()
    mock_rate_limiter.check_message_submission.side_effect = lambda ip, s_id, db: call_order.append("check_rate_limit")
    mock_rate_limiter.record_message_submission.side_effect = lambda ip, s_id, db: call_order.append("record_submission")

    monkeypatch.setattr(
        "backend.app.api.v1.routes.public_support.support_rate_limiter", mock_rate_limiter
    )

    session_id = uuid.uuid4()
    merchant_id = uuid.uuid4()
    mock_session = CustomerSupportSession(
        id=session_id,
        merchant_id=merchant_id,
        customer_token_hash="dummy_hash",
        status="active",
    )
    from datetime import datetime, timezone
    mock_message = CustomerSupportMessage(
        id=uuid.uuid4(),
        session_id=session_id,
        merchant_id=merchant_id,
        customer_text="Legitimate inquiry",
        status="needs_review",
        created_at=datetime.now(timezone.utc),
    )

    mock_service = MagicMock()
    def mock_verify(s_id, token):
        call_order.append("verify_token")
        return mock_session

    def mock_submit(session_id, customer_token=None, content="", session=None):
        call_order.append("submit_inquiry")
        return mock_message

    mock_service.verify_customer_session.side_effect = mock_verify
    mock_service.submit_customer_inquiry.side_effect = mock_submit

    monkeypatch.setattr(
        "backend.app.api.v1.routes.public_support.CustomerSupportService",
        lambda db, llm_provider=None: mock_service,
    )

    req = CustomerInquiryRequest(content="Legitimate inquiry")
    res = submit_customer_inquiry(
        session_id=session_id,
        req=req,
        request=mock_request,
        x_customer_token="valid_secret_token",
        db=mock_db,
        llm_provider=MagicMock(),
    )

    assert res.id == mock_message.id
    assert res.customer_text == "Legitimate inquiry"

    # Verify execution sequence: check -> verify -> record -> submit
    assert call_order == ["check_rate_limit", "verify_token", "record_submission", "submit_inquiry"]
