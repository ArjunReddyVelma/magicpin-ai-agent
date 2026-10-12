import time
import uuid
import hmac
import secrets
import hashlib
from typing import Dict, List
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


class LoginRateLimiter:
    """
    In-memory rate limiter for login attempts to mitigate brute-force attacks.
    Tracks failure timestamps per identifier (IP or normalized email).
    """

    def __init__(self, max_attempts: int = 5, window_seconds: int = 900):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        # key -> list of failure timestamps
        self._failures: Dict[str, List[float]] = {}

    def is_rate_limited(self, key: str) -> bool:
        now = time.time()
        cutoff = now - self.window_seconds
        attempts = [t for t in self._failures.get(key, []) if t > cutoff]
        self._failures[key] = attempts
        return len(attempts) >= self.max_attempts

    def record_failure(self, key: str) -> None:
        now = time.time()
        cutoff = now - self.window_seconds
        attempts = [t for t in self._failures.get(key, []) if t > cutoff]
        attempts.append(now)
        self._failures[key] = attempts

    def reset(self, key: str) -> None:
        if key in self._failures:
            del self._failures[key]


login_rate_limiter = LoginRateLimiter(
    max_attempts=settings.RATE_LIMIT_LOGIN_MAX_ATTEMPTS,
    window_seconds=settings.RATE_LIMIT_LOGIN_WINDOW_SECONDS,
)
