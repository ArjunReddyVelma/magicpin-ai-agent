import uuid
import time
from backend.app.core.security import (
    hash_password,
    verify_password,
    generate_session_token,
    hash_session_token,
    generate_csrf_token,
    verify_csrf_token,
    LoginRateLimiter,
)


def test_argon2id_hashing():
    pw = "SuperSecret123!"
    hashed = hash_password(pw)
    assert hashed.startswith("$argon2id$")
    assert verify_password(pw, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False
    assert verify_password(pw, "invalid_hash_string") is False


def test_opaque_session_tokens():
    token1 = generate_session_token()
    token2 = generate_session_token()
    assert token1 != token2
    assert len(token1) >= 40  # base64url of 32 bytes is ~43 chars

    hash1 = hash_session_token(token1)
    hash2 = hash_session_token(token2)
    assert len(hash1) == 64
    assert hash1 != hash2
    # Deterministic hashing
    assert hash_session_token(token1) == hash1


def test_session_bound_csrf_tokens():
    session_id = uuid.uuid4()
    user_id = uuid.uuid4()
    other_session_id = uuid.uuid4()

    csrf = generate_csrf_token(session_id, user_id)
    assert len(csrf) == 64

    # Valid token verification
    assert verify_csrf_token(csrf, session_id, user_id) is True

    # Tampered token verification
    tampered = csrf[:-4] + "abcd"
    assert verify_csrf_token(tampered, session_id, user_id) is False

    # Bound to session: token from session 1 rejected for session 2
    assert verify_csrf_token(csrf, other_session_id, user_id) is False

    # Never exposes raw session or matches raw session
    raw_token = generate_session_token()
    assert csrf != raw_token
    assert csrf != hash_session_token(raw_token)


def test_login_rate_limiter():
    limiter = LoginRateLimiter(max_attempts=3, window_seconds=10)
    key = "127.0.0.1:test@example.com"

    assert limiter.is_rate_limited(key) is False

    limiter.record_failure(key)
    limiter.record_failure(key)
    assert limiter.is_rate_limited(key) is False

    limiter.record_failure(key)
    # 3 failures reach limit
    assert limiter.is_rate_limited(key) is True

    # Reset clears limit
    limiter.reset(key)
    assert limiter.is_rate_limited(key) is False
