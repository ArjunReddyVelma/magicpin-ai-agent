import uuid
import pytest
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import create_engine

from backend.app.core.config import settings
from backend.app.core.security import PostgreSQLLoginRateLimiter
from backend.app.db.session import check_database_connection


def test_postgresql_rate_limiter_cross_instance_sharing(db_session: Session):
    """
    SECURITY TEST: Proves that separate rate limiter instances (simulating
    stateless distributed backend nodes) share failed attempt state via PostgreSQL.
    """
    key = f"127.0.0.1:user_{uuid.uuid4().hex[:8]}@example.com"
    limiter_instance_a = PostgreSQLLoginRateLimiter(max_attempts=3, window_seconds=60)
    limiter_instance_b = PostgreSQLLoginRateLimiter(max_attempts=3, window_seconds=60)

    # Initial check on both instances
    assert limiter_instance_a.is_rate_limited(key, db=db_session) is False
    assert limiter_instance_b.is_rate_limited(key, db=db_session) is False

    # Instance A records 2 failures
    limiter_instance_a.record_failure(key, db=db_session, email="test@example.com", ip="127.0.0.1")
    limiter_instance_a.record_failure(key, db=db_session, email="test@example.com", ip="127.0.0.1")

    # Instance B sees the 2 failures recorded by Instance A
    assert limiter_instance_b.is_rate_limited(key, db=db_session) is False

    # Instance B records the 3rd failure
    limiter_instance_b.record_failure(key, db=db_session, email="test@example.com", ip="127.0.0.1")

    # Both instances now report rate limited
    assert limiter_instance_a.is_rate_limited(key, db=db_session) is True
    assert limiter_instance_b.is_rate_limited(key, db=db_session) is True


def test_postgresql_rate_limiter_persistence_across_restarts():
    """
    SECURITY TEST: Proves that rate-limiting state persists in PostgreSQL
    and remains active across application restarts (separate DB connections and limiter lifecycles).
    """
    key = f"192.168.1.10:brute_{uuid.uuid4().hex[:8]}@example.com"
    test_engine = create_engine(settings.DATABASE_URL_TEST)
    if not check_database_connection(test_engine):
        test_engine.dispose()
        pytest.skip("Test database (DATABASE_URL_TEST) is unavailable; skipping restart persistence test.")
    SessionMaker = sessionmaker(bind=test_engine)

    # Simulate Process 1: 3 failures recorded
    session_1 = SessionMaker()
    try:
        limiter_proc_1 = PostgreSQLLoginRateLimiter(max_attempts=3, window_seconds=60)
        for _ in range(3):
            limiter_proc_1.record_failure(key, db=session_1, email="brute@example.com", ip="192.168.1.10")
        assert limiter_proc_1.is_rate_limited(key, db=session_1) is True
    finally:
        session_1.close()

    # Simulate Process Restart: Process 1 dies, Process 2 starts with fresh memory
    session_2 = SessionMaker()
    try:
        limiter_proc_2 = PostgreSQLLoginRateLimiter(max_attempts=3, window_seconds=60)
        # Even with completely empty in-memory state, PostgreSQL enforces the rate limit
        assert limiter_proc_2.is_rate_limited(key, db=session_2) is True

        # Successful login in Process 2 resets the counter
        limiter_proc_2.record_success(key, db=session_2, email="brute@example.com", ip="192.168.1.10")
        assert limiter_proc_2.is_rate_limited(key, db=session_2) is False
    finally:
        session_2.close()
        test_engine.dispose()
