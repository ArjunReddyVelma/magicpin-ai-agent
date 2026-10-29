import uuid
from unittest.mock import MagicMock
import pytest
from fastapi import HTTPException
from sqlalchemy.exc import OperationalError

from backend.app.core.config import settings
from backend.app.core.support_rate_limiter import (
    PublicSupportRateLimiter,
    derive_advisory_lock_id,
)
from backend.app.models.audit_event import AuditEvent


def test_deterministic_lock_id_derivation_bounds_and_consistency():
    """
    Unit test: Verifies that derive_advisory_lock_id deterministically maps arbitrary
    string keys to 64-bit signed integers in range [-2^63, 2^63 - 1] suitable for
    PostgreSQL pg_advisory_xact_lock(bigint).
    """
    key1 = "support_msg_ip:192.168.1.100"
    key2 = "support_msg_session:123e4567-e89b-12d3-a456-426614174000"
    key3 = "support_session:10.0.0.1"

    id1_a = derive_advisory_lock_id(key1)
    id1_b = derive_advisory_lock_id(key1)
    assert id1_a == id1_b, "Lock derivation must be strictly deterministic"

    id2 = derive_advisory_lock_id(key2)
    id3 = derive_advisory_lock_id(key3)
    assert id1_a != id2, "Different keys should produce distinct 64-bit lock IDs"
    assert id2 != id3, "Different keys should produce distinct 64-bit lock IDs"

    min_int64 = -(2**63)
    max_int64 = 2**63 - 1
    for lid in (id1_a, id2, id3):
        assert isinstance(lid, int)
        assert min_int64 <= lid <= max_int64, f"Lock ID {lid} out of 64-bit signed range"


def test_batch_atomic_commit_persists_both_events_in_one_transaction():
    """
    Unit test: Verifies that record_message_submission prepares both IP and session events,
    adds them via db.add_all, and executes a single atomic db.commit().
    """
    limiter = PublicSupportRateLimiter(message_ip_limit=10, message_session_limit=10)
    mock_db = MagicMock()
    mock_db.bind = None  # Non-PostgreSQL dialect in mock unit test

    # Mock count queries to return 0 (under limit)
    mock_db.scalar.return_value = 0

    client_ip = "192.168.1.50"
    session_id = uuid.uuid4()

    limiter.record_message_submission(client_ip, session_id, db=mock_db)

    # Verify atomic batch insertion
    mock_db.add_all.assert_called_once()
    added_events = mock_db.add_all.call_args[0][0]
    assert len(added_events) == 2

    ip_event, sess_event = added_events
    assert isinstance(ip_event, AuditEvent)
    assert ip_event.event_type == "support.message_submit_ip"
    assert ip_event.metadata_json["key"] == f"support_msg_ip:{client_ip}"
    assert ip_event.metadata_json["ip"] == client_ip

    assert isinstance(sess_event, AuditEvent)
    assert sess_event.event_type == "support.message_submit_session"
    assert sess_event.metadata_json["key"] == f"support_msg_session:{session_id}"
    assert sess_event.metadata_json["session_id"] == str(session_id)

    # Exactly one commit for the batch
    mock_db.commit.assert_called_once()
    mock_db.rollback.assert_not_called()


def test_batch_rollback_on_commit_failure(monkeypatch):
    """
    Unit test: Verifies that if db.commit() raises an exception during batch insertion,
    db.rollback() is immediately invoked and the transaction is cleanly aborted.
    In testing environment, the exception is re-raised.
    """
    monkeypatch.setattr(settings, "APP_ENV", "testing")

    limiter = PublicSupportRateLimiter()
    mock_db = MagicMock()
    mock_db.bind = None
    mock_db.scalar.return_value = 0
    mock_db.commit.side_effect = OperationalError("DB Connection Dropped", params=None, orig=Exception("dropped"))

    client_ip = "192.168.1.50"
    session_id = uuid.uuid4()

    with pytest.raises(OperationalError):
        limiter.record_message_submission(client_ip, session_id, db=mock_db)

    # Verify rollback was called to clear transaction state
    mock_db.rollback.assert_called_once()


def test_production_persistence_failure_raises_503(monkeypatch):
    """
    Unit test: Verifies that in production (APP_ENV='production'), database persistence
    failures fail closed with HTTP 503 DEPENDENCY_UNAVAILABLE instead of silently proceeding.
    """
    monkeypatch.setattr(settings, "APP_ENV", "production")

    limiter = PublicSupportRateLimiter()
    mock_db = MagicMock()
    mock_db.bind = None
    mock_db.scalar.return_value = 0
    mock_db.commit.side_effect = Exception("Disk Full in Production")

    client_ip = "192.168.1.50"
    session_id = uuid.uuid4()

    with pytest.raises(HTTPException) as exc_info:
        limiter.record_message_submission(client_ip, session_id, db=mock_db)

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["error"]["code"] == "DEPENDENCY_UNAVAILABLE"
    mock_db.rollback.assert_called_once()


def test_development_fallback_behavior(monkeypatch):
    """
    Unit test: Verifies that in development (APP_ENV='development'), database commit
    failure rolls back and safely falls back to in-memory event tracking.
    """
    monkeypatch.setattr(settings, "APP_ENV", "development")

    limiter = PublicSupportRateLimiter(message_ip_limit=2, message_session_limit=2)
    mock_db = MagicMock()
    mock_db.bind = None
    mock_db.scalar.return_value = 0
    mock_db.commit.side_effect = Exception("Transient Local DB Glitch")

    client_ip = "192.168.1.50"
    session_id = uuid.uuid4()

    # First attempt: commit fails, falls back to memory (count=1)
    limiter.record_message_submission(client_ip, session_id, db=mock_db)
    mock_db.rollback.assert_called_once()

    # Second attempt: falls back to memory (count=2)
    limiter.record_message_submission(client_ip, session_id, db=mock_db)

    # Third attempt: in-memory quota is exhausted -> 429
    with pytest.raises(HTTPException) as exc_info:
        limiter.record_message_submission(client_ip, session_id, db=mock_db)
    assert exc_info.value.status_code == 429
    assert exc_info.value.detail["error"]["code"] == "RATE_LIMIT_EXCEEDED"


def test_recheck_inside_lock_raises_429_if_concurrency_exceeded():
    """
    Unit test: Verifies that if concurrent requests consume quota while waiting for lock,
    the re-check inside record_message_submission raises HTTP 429 and does NOT commit.
    """
    limiter = PublicSupportRateLimiter(message_ip_limit=2, message_session_limit=2)
    mock_db = MagicMock()
    mock_db.bind = None

    # Simulate recheck query returning 2 (quota reached by another worker)
    mock_db.scalar.return_value = 2

    client_ip = "192.168.1.50"
    session_id = uuid.uuid4()

    with pytest.raises(HTTPException) as exc_info:
        limiter.record_message_submission(client_ip, session_id, db=mock_db)

    assert exc_info.value.status_code == 429
    assert exc_info.value.detail["error"]["code"] == "RATE_LIMIT_EXCEEDED"
    mock_db.add_all.assert_not_called()
    mock_db.commit.assert_not_called()
    mock_db.rollback.assert_called_once()
