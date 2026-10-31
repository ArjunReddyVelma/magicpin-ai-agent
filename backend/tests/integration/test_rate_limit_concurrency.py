"""
Integration and Concurrency Tests for Reliable PostgreSQL Rate Limiting.

Verifies:
1. True multi-threaded concurrency using threading.Barrier against PostgreSQL.
2. Advisory locking via pg_advisory_xact_lock(bigint) with deterministic sorted ordering.
3. Concurrency-safe quota enforcement: prevents TOCTOU race conditions where concurrent
   workers exceed configured IP or session quotas.
4. Atomic batch persistence: both IP and session events persist in a single transaction;
   failures rollback both events cleanly leaving zero partial state.
5. Deadlock freedom across intersecting IP and session locks.
6. Lock timeout behavior fail-closed in production.
"""
import uuid
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import List, Tuple

import pytest
from fastapi import HTTPException
from sqlalchemy import text, select, func, event
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError

from backend.tests.conftest import TestingSessionLocal, test_engine
from backend.app.core.config import settings
from backend.app.core.db_safety import validate_test_database_isolation
from backend.app.db.session import check_database_connection
from backend.app.models.audit_event import AuditEvent
from backend.app.core.support_rate_limiter import (
    PublicSupportRateLimiter,
    derive_advisory_lock_id,
    DISPOSABLE_SUPPORT_EVENT_TYPES,
)


@pytest.fixture(autouse=True)
def require_test_database():
    """
    Ensures safe database isolation and automatically skips if PostgreSQL
    service is unavailable (e.g. running unit tests locally without local Postgres).
    """
    validate_test_database_isolation()
    if not check_database_connection(test_engine):
        pytest.skip("Test database (DATABASE_URL_TEST) is unavailable; skipping PostgreSQL concurrency test.")


def _cleanup_audit_keys(keys: List[str]):
    """Helper to remove ephemeral test records from PostgreSQL."""
    db: Session = TestingSessionLocal()
    try:
        for k in keys:
            db.query(AuditEvent).filter(
                AuditEvent.target_type == "public_support",
                AuditEvent.metadata_json["key"].astext == k,
            ).delete(synchronize_session=False)
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def test_atomic_batch_commit_persists_both_events_in_postgresql():
    """
    Verifies that record_message_submission writes both IP and session audit events
    in a single atomic transaction in real PostgreSQL.
    """
    limiter = PublicSupportRateLimiter()
    test_ip = f"10.250.1.{uuid.uuid4().hex[:4]}"
    session_id = uuid.uuid4()
    ip_key = f"support_msg_ip:{test_ip}"
    session_key = f"support_msg_session:{session_id}"

    db: Session = TestingSessionLocal()
    try:
        limiter.record_message_submission(test_ip, session_id, db=db)

        # Verify both events exist in the database
        events = db.query(AuditEvent).filter(
            AuditEvent.target_type == "public_support",
            AuditEvent.metadata_json["key"].astext.in_([ip_key, session_key]),
        ).all()
        assert len(events) == 2

        event_types = {e.event_type for e in events}
        assert event_types == {"support.message_submit_ip", "support.message_submit_session"}
    finally:
        db.close()
        _cleanup_audit_keys([ip_key, session_key])


def test_atomic_rollback_on_failure_leaves_zero_events_in_postgresql(monkeypatch):
    """
    Verifies that if an error occurs during batch persistence (e.g. database commit failure
    midway after rows have been flushed to PostgreSQL), the transaction is cleanly rolled back
    and zero partial events remain in PostgreSQL.
    """
    monkeypatch.setattr(settings, "APP_ENV", "testing")
    limiter = PublicSupportRateLimiter()
    test_ip = f"10.250.2.{uuid.uuid4().hex[:4]}"
    session_id = uuid.uuid4()
    ip_key = f"support_msg_ip:{test_ip}"
    session_key = f"support_msg_session:{session_id}"

    db: Session = TestingSessionLocal()

    def failing_before_commit(session):
        raise OperationalError(
            "Simulated database failure during commit",
            params=None,
            orig=Exception("Commit failed midway"),
        )

    event.listen(db, "before_commit", failing_before_commit)

    try:
        # Pre-check zero events in PostgreSQL using a clean session
        check_db: Session = TestingSessionLocal()
        try:
            assert check_db.query(AuditEvent).filter(
                AuditEvent.metadata_json["key"].astext.in_([ip_key, session_key])
            ).count() == 0
        finally:
            check_db.close()

        # Execute submission with failing commit; verify it raises OperationalError
        with pytest.raises(OperationalError):
            limiter.record_message_submission(test_ip, session_id, db=db)

        # Query database using a fresh transaction/session to confirm zero partial events remain
        verify_db: Session = TestingSessionLocal()
        try:
            count_after = verify_db.query(AuditEvent).filter(
                AuditEvent.target_type == "public_support",
                AuditEvent.metadata_json["key"].astext.in_([ip_key, session_key]),
            ).count()
            assert count_after == 0, f"Expected 0 events after rollback, found {count_after}"
        finally:
            verify_db.close()
    finally:
        event.remove(db, "before_commit", failing_before_commit)
        db.close()
        _cleanup_audit_keys([ip_key, session_key])


def test_concurrent_session_quota_enforcement():
    """
    Proves that concurrent worker threads simultaneously submitting messages to the
    SAME session cannot exceed the configured session quota.
    Uses threading.Barrier to ensure all threads execute simultaneously.
    """
    quota_limit = 4
    num_threads = 10

    limiter = PublicSupportRateLimiter(message_session_limit=quota_limit)
    shared_session_id = uuid.uuid4()
    session_key = f"support_msg_session:{shared_session_id}"
    cleaned_keys = [session_key]

    barrier = threading.Barrier(num_threads)
    results: List[Tuple[bool, str]] = []
    results_lock = threading.Lock()

    def worker(worker_id: int):
        worker_ip = f"10.250.3.{worker_id}"
        with results_lock:
            cleaned_keys.append(f"support_msg_ip:{worker_ip}")
        worker_db: Session = TestingSessionLocal()
        try:
            # Synchronize all threads right before executing
            barrier.wait(timeout=5.0)
            limiter.record_message_submission(worker_ip, shared_session_id, db=worker_db)
            with results_lock:
                results.append((True, "success"))
        except HTTPException as he:
            with results_lock:
                results.append((False, f"HTTP {he.status_code}: {he.detail}"))
        except Exception as e:
            with results_lock:
                results.append((False, f"Error: {e}"))
        finally:
            worker_db.close()

    try:
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(worker, i) for i in range(num_threads)]
            for f in futures:
                f.result()

        successes = [r for r in results if r[0]]
        failures = [r for r in results if not r[0]]

        # Exactly quota_limit submissions must succeed
        assert len(successes) == quota_limit, (
            f"Expected exactly {quota_limit} successes, got {len(successes)}. Results: {results}"
        )
        assert len(failures) == num_threads - quota_limit
        for _, detail in failures:
            assert "429" in detail

        # Verify PostgreSQL database row count matches exactly quota_limit
        verify_db: Session = TestingSessionLocal()
        try:
            db_count = verify_db.query(AuditEvent).filter(
                AuditEvent.target_type == "public_support",
                AuditEvent.metadata_json["key"].astext == session_key,
            ).count()
            assert db_count == quota_limit, f"Expected {quota_limit} rows in DB, found {db_count}"
        finally:
            verify_db.close()
    finally:
        _cleanup_audit_keys(cleaned_keys)


def test_concurrent_ip_quota_enforcement():
    """
    Proves that concurrent worker threads simultaneously submitting messages from the
    SAME IP across different sessions cannot exceed the configured IP quota.
    """
    quota_limit = 3
    num_threads = 8

    limiter = PublicSupportRateLimiter(message_ip_limit=quota_limit)
    shared_ip = f"10.250.4.{uuid.uuid4().hex[:4]}"
    ip_key = f"support_msg_ip:{shared_ip}"
    cleaned_keys = [ip_key]

    barrier = threading.Barrier(num_threads)
    results: List[Tuple[bool, str]] = []
    results_lock = threading.Lock()

    def worker():
        worker_session_id = uuid.uuid4()
        with results_lock:
            cleaned_keys.append(f"support_msg_session:{worker_session_id}")
        worker_db: Session = TestingSessionLocal()
        try:
            barrier.wait(timeout=5.0)
            limiter.record_message_submission(shared_ip, worker_session_id, db=worker_db)
            with results_lock:
                results.append((True, "success"))
        except HTTPException as he:
            with results_lock:
                results.append((False, f"HTTP {he.status_code}: {he.detail}"))
        except Exception as e:
            with results_lock:
                results.append((False, f"Error: {e}"))
        finally:
            worker_db.close()

    try:
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(worker) for _ in range(num_threads)]
            for f in futures:
                f.result()

        successes = [r for r in results if r[0]]
        failures = [r for r in results if not r[0]]

        assert len(successes) == quota_limit
        assert len(failures) == num_threads - quota_limit
        for _, detail in failures:
            assert "429" in detail

        # Verify DB row count
        verify_db: Session = TestingSessionLocal()
        try:
            db_count = verify_db.query(AuditEvent).filter(
                AuditEvent.target_type == "public_support",
                AuditEvent.metadata_json["key"].astext == ip_key,
            ).count()
            assert db_count == quota_limit
        finally:
            verify_db.close()
    finally:
        _cleanup_audit_keys(cleaned_keys)


def test_concurrent_session_creation_quota_enforcement():
    """
    Proves that concurrent worker threads simultaneously creating customer support
    sessions from the SAME IP address cannot exceed the configured session creation quota.
    Uses threading.Barrier to ensure real simultaneous execution against PostgreSQL.
    """
    quota_limit = 3
    num_threads = 8

    limiter = PublicSupportRateLimiter(session_create_limit=quota_limit)
    shared_ip = f"10.250.8.{uuid.uuid4().hex[:4]}"
    key = f"support_session:{shared_ip}"
    cleaned_keys = [key]

    barrier = threading.Barrier(num_threads)
    results: List[Tuple[bool, str]] = []
    results_lock = threading.Lock()

    def worker():
        worker_db: Session = TestingSessionLocal()
        try:
            barrier.wait(timeout=5.0)
            limiter.record_session_creation(shared_ip, db=worker_db)
            with results_lock:
                results.append((True, "success"))
        except HTTPException as he:
            with results_lock:
                results.append((False, f"HTTP {he.status_code}: {he.detail}"))
        except Exception as e:
            with results_lock:
                results.append((False, f"Error: {e}"))
        finally:
            worker_db.close()

    try:
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(worker) for _ in range(num_threads)]
            for f in futures:
                f.result()

        successes = [r for r in results if r[0]]
        failures = [r for r in results if not r[0]]

        # Exactly quota_limit requests must succeed
        assert len(successes) == quota_limit, (
            f"Expected exactly {quota_limit} successes, got {len(successes)}. Results: {results}"
        )
        # Remaining requests must fail with HTTP 429
        assert len(failures) == num_threads - quota_limit
        for _, detail in failures:
            assert "429" in detail

        # Exactly quota_limit events are persisted in PostgreSQL
        verify_db: Session = TestingSessionLocal()
        try:
            db_count = verify_db.query(AuditEvent).filter(
                AuditEvent.target_type == "public_support",
                AuditEvent.metadata_json["key"].astext == key,
            ).count()
            assert db_count == quota_limit, f"Expected {quota_limit} rows in DB, found {db_count}"
        finally:
            verify_db.close()
    finally:
        _cleanup_audit_keys(cleaned_keys)


def test_independent_keys_do_not_block_or_interfere():
    """
    Verifies that concurrent requests touching completely independent IPs and sessions
    proceed without blocking or serialization conflicts.
    """
    limiter = PublicSupportRateLimiter()
    num_workers = 6
    barrier = threading.Barrier(num_workers)
    cleaned_keys = []
    keys_lock = threading.Lock()

    def worker(worker_id: int):
        w_ip = f"10.250.5.{worker_id}"
        w_session = uuid.uuid4()
        with keys_lock:
            cleaned_keys.extend([f"support_msg_ip:{w_ip}", f"support_msg_session:{w_session}"])

        worker_db: Session = TestingSessionLocal()
        try:
            barrier.wait(timeout=5.0)
            limiter.record_message_submission(w_ip, w_session, db=worker_db)
            return True
        finally:
            worker_db.close()

    try:
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = [executor.submit(worker, i) for i in range(num_workers)]
            for f in futures:
                assert f.result() is True
    finally:
        _cleanup_audit_keys(cleaned_keys)


def test_deadlock_freedom_with_inverted_lock_request_order():
    """
    Proves that deterministic lock ID ordering (sorted ascending) eliminates deadlocks
    even when two workers acquire locks over intersecting key sets in opposing order.
    """
    limiter = PublicSupportRateLimiter()
    key_a = f"support_msg_ip:10.250.6.1"
    key_b = f"support_msg_session:{uuid.uuid4()}"
    cleaned_keys = [key_a, key_b]

    # Worker 1 requests [key_a, key_b]
    # Worker 2 requests [key_b, key_a]
    num_iterations = 10
    barrier = threading.Barrier(2)
    errors = []

    def worker_a():
        for _ in range(num_iterations):
            db: Session = TestingSessionLocal()
            try:
                barrier.wait(timeout=5.0)
                limiter._acquire_advisory_locks(db, [derive_advisory_lock_id(key_a), derive_advisory_lock_id(key_b)])
                db.commit()
            except Exception as e:
                errors.append(f"Worker A error: {e}")
                db.rollback()
            finally:
                db.close()

    def worker_b():
        for _ in range(num_iterations):
            db: Session = TestingSessionLocal()
            try:
                barrier.wait(timeout=5.0)
                limiter._acquire_advisory_locks(db, [derive_advisory_lock_id(key_b), derive_advisory_lock_id(key_a)])
                db.commit()
            except Exception as e:
                errors.append(f"Worker B error: {e}")
                db.rollback()
            finally:
                db.close()

    try:
        t1 = threading.Thread(target=worker_a)
        t2 = threading.Thread(target=worker_b)
        t1.start()
        t2.start()
        t1.join(timeout=10.0)
        t2.join(timeout=10.0)

        assert not t1.is_alive(), "Worker A deadlocked!"
        assert not t2.is_alive(), "Worker B deadlocked!"
        assert len(errors) == 0, f"Errors encountered: {errors}"
    finally:
        _cleanup_audit_keys(cleaned_keys)


def test_lock_timeout_handling_fails_closed_in_production(monkeypatch):
    """
    Verifies that if an advisory lock cannot be acquired within the timeout window,
    in production the request fails closed with HTTP 503 DEPENDENCY_UNAVAILABLE.
    """
    monkeypatch.setattr(settings, "APP_ENV", "production")
    limiter = PublicSupportRateLimiter()

    test_ip = f"10.250.7.{uuid.uuid4().hex[:4]}"
    session_id = uuid.uuid4()
    lock_id = derive_advisory_lock_id(f"support_msg_ip:{test_ip}")

    # Connection 1 acquires the advisory lock and holds it
    holder_db: Session = TestingSessionLocal()
    holder_db.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": lock_id})

    # Connection 2 attempts to record submission for the locked key with short timeout
    worker_db: Session = TestingSessionLocal()
    try:
        # Override lock timeout on worker connection to be fast (100ms)
        worker_db.execute(text("SET LOCAL lock_timeout = '100ms';"))

        with pytest.raises(HTTPException) as exc_info:
            limiter.record_message_submission(test_ip, session_id, db=worker_db)

        assert exc_info.value.status_code == 503
        assert exc_info.value.detail["error"]["code"] == "DEPENDENCY_UNAVAILABLE"
    finally:
        worker_db.close()
        holder_db.rollback()
        holder_db.close()
