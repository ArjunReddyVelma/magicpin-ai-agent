import time
import uuid
import hmac
import secrets
import hashlib
from typing import Dict, List, Optional, Any
from argon2 import PasswordHasher, Type
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError

from backend.app.core.config import settings

# Argon2id hasher configured per security requirements
# Minimum 19 MiB memory cost (19456 KiB), 2 iterations, 1 parallelism thread, 128-bit (16-byte) salt
_hasher = PasswordHasher(
    time_cost=2,
    memory_cost=19456,
    parallelism=1,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)


def hash_password(password: str) -> str:
    """Hashes a plaintext password using Argon2id."""
    return _hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    """Verifies a plaintext password against an Argon2id hash."""
    try:
        return _hasher.verify(hashed, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def generate_session_token() -> str:
    """Generates a cryptographically strong 32-byte URL-safe session token."""
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    """Computes SHA-256 hash of a session token for secure database storage."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_csrf_token(session_id: uuid.UUID, user_id: uuid.UUID) -> str:
    """
    Generates a cryptographically secure, session-bound CSRF token.
    Never exposes or derives the CSRF token directly from the raw session cookie.
    Bound to the server-side session UUID, user UUID, and CSRF secret.
    """
    message = f"csrf:{session_id}:{user_id}".encode("utf-8")
    return hmac.new(
        settings.CSRF_SECRET.encode("utf-8"), message, hashlib.sha256
    ).hexdigest()


def verify_csrf_token(submitted_token: str, session_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    """
    Verifies a submitted CSRF token against the expected session-bound token in constant time.
    """
    if not submitted_token:
        return False
    expected = generate_csrf_token(session_id, user_id)
    return hmac.compare_digest(submitted_token.strip(), expected)


from datetime import datetime, timedelta, timezone
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from backend.app.models.audit_event import AuditEvent


class PostgreSQLLoginRateLimiter:
    """
    PostgreSQL-backed login rate limiter utilizing the audit_events table.
    Enforces shared, stateless rate-limiting across distributed API instances
    without introducing external cache dependencies like Redis.
    Falls back to in-memory tracking if db session is None.
    """

    def __init__(self, max_attempts: int = 5, window_seconds: int = 900):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._memory_failures: Dict[str, List[float]] = {}

    def is_rate_limited(self, key: str, db: Optional[Session] = None) -> bool:
        if db is None:
            now = time.time()
            cutoff = now - self.window_seconds
            attempts = [t for t in self._memory_failures.get(key, []) if t > cutoff]
            self._memory_failures[key] = attempts
            return len(attempts) >= self.max_attempts

        now_utc = datetime.now(timezone.utc)
        cutoff_dt = now_utc - timedelta(seconds=self.window_seconds)

        # Check latest success event for this key
        last_success_stmt = (
            select(func.max(AuditEvent.created_at))
            .where(
                AuditEvent.event_type == "auth.login_success",
                AuditEvent.metadata_json.op("->>")("key") == key,
            )
        )
        last_success = db.scalar(last_success_stmt)
        if last_success is not None:
            if last_success.tzinfo is None:
                last_success = last_success.replace(tzinfo=timezone.utc)
            if last_success > cutoff_dt:
                cutoff_dt = last_success

        failure_count_stmt = (
            select(func.count(AuditEvent.id))
            .where(
                AuditEvent.event_type == "auth.login_failure",
                AuditEvent.metadata_json.op("->>")("key") == key,
                AuditEvent.created_at >= cutoff_dt,
            )
        )
        count = db.scalar(failure_count_stmt) or 0
        return count >= self.max_attempts

    def record_failure(
        self,
        key: str,
        db: Optional[Session] = None,
        email: Optional[str] = None,
        ip: Optional[str] = None,
        user_id: Optional[uuid.UUID] = None,
    ) -> None:
        if db is None:
            now = time.time()
            cutoff = now - self.window_seconds
            attempts = [t for t in self._memory_failures.get(key, []) if t > cutoff]
            attempts.append(now)
            self._memory_failures[key] = attempts
            return

        event = AuditEvent(
            user_id=user_id,
            merchant_id=None,
            event_type="auth.login_failure",
            target_type="login_attempt",
            metadata_json={
                "key": key,
                "email": email or "",
                "ip": ip or "",
            },
            created_at=datetime.now(timezone.utc),
        )
        db.add(event)
        db.commit()

    def record_success(
        self,
        key: str,
        db: Optional[Session] = None,
        email: Optional[str] = None,
        ip: Optional[str] = None,
        user_id: Optional[uuid.UUID] = None,
        merchant_id: Optional[uuid.UUID] = None,
    ) -> None:
        if db is None:
            if key in self._memory_failures:
                del self._memory_failures[key]
            return

        event = AuditEvent(
            user_id=user_id,
            merchant_id=merchant_id,
            event_type="auth.login_success",
            target_type="login_attempt",
            metadata_json={
                "key": key,
                "email": email or "",
                "ip": ip or "",
            },
            created_at=datetime.now(timezone.utc),
        )
        db.add(event)
        db.commit()

    def reset(self, key: str, db: Optional[Session] = None) -> None:
        if db is None:
            if key in self._memory_failures:
                del self._memory_failures[key]
            return

        event = AuditEvent(
            event_type="auth.login_success",
            target_type="login_attempt",
            metadata_json={"key": key},
            created_at=datetime.now(timezone.utc),
        )
        db.add(event)
        db.commit()


# Alias for backward compatibility
LoginRateLimiter = PostgreSQLLoginRateLimiter

login_rate_limiter = PostgreSQLLoginRateLimiter(
    max_attempts=settings.RATE_LIMIT_LOGIN_MAX_ATTEMPTS,
    window_seconds=settings.RATE_LIMIT_LOGIN_WINDOW_SECONDS,
)
