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


import ipaddress
from typing import Union, Set
from fastapi import Request


def parse_trusted_proxies(
    configured: Optional[Union[str, List[str], Set[str]]] = None,
) -> List[Union[ipaddress.IPv4Network, ipaddress.IPv6Network]]:
    """
    Parses configured trusted proxy IPs and CIDR networks into ipaddress network objects.
    Defaults to settings.TRUSTED_PROXIES if configured is None.
    """
    if configured is None:
        configured = getattr(settings, "TRUSTED_PROXIES", "127.0.0.1,::1")

    if isinstance(configured, str):
        items = [item.strip() for item in configured.split(",") if item.strip()]
    else:
        items = [str(item).strip() for item in configured if str(item).strip()]

    networks: List[Union[ipaddress.IPv4Network, ipaddress.IPv6Network]] = []
    for item in items:
        try:
            # Handles both CIDR notation (e.g. 10.0.0.0/8) and individual IPs (127.0.0.1)
            net = ipaddress.ip_network(item, strict=False)
            networks.append(net)
        except ValueError:
            # Malformed or unparseable proxy network definition is safely ignored
            continue
    return networks


def _clean_ip_candidate(candidate: str) -> Optional[str]:
    """
    Sanitizes and extracts an IP address string from a raw candidate hop.
    Handles port stripping (IPv4 with port, IPv6 in brackets with port).
    Returns None if the candidate cannot be parsed as a valid IP.
    """
    if not candidate:
        return None

    cleaned = candidate.strip().strip('"').strip("'")
    if not cleaned:
        return None

    # Handle bracketed IPv6, e.g. [2001:db8::1] or [2001:db8::1]:8080
    if cleaned.startswith("[") and "]" in cleaned:
        bracket_end = cleaned.find("]")
        cleaned = cleaned[1:bracket_end]
    elif cleaned.count(":") == 1:
        # IPv4 with port, e.g. 203.0.113.195:443
        cleaned = cleaned.split(":")[0]

    try:
        addr = ipaddress.ip_address(cleaned)
        return str(addr)
    except ValueError:
        return None


def get_client_ip(
    request: Request,
    trusted_proxies: Optional[Union[str, List[str], Set[str]]] = None,
) -> str:
    """
    Extracts the authentic client IP address from an incoming HTTP request.

    Security model & spoof-prevention rules:
    1. Obtains the immediate TCP peer address from request.client.host.
    2. If request.client is None or peer_ip is invalid/empty, returns 'unknown'.
    3. Resolves the configured list of trusted proxies (from trusted_proxies or settings.TRUSTED_PROXIES).
    4. UNTRUSTED PEER BOUNDARY: If the immediate peer address is NOT in the trusted proxy list,
       forwarding headers (X-Forwarded-For) are STRICTLY IGNORED. The immediate peer address
       is returned. This prevents arbitrary clients from spoofing their IP.
    5. TRUSTED PROXY TRAVERSAL: If the immediate peer IS a trusted proxy:
       - Parses X-Forwarded-For header values into individual hops.
       - Traverses hops from RIGHT TO LEFT (most recent proxy to earliest).
       - Each hop is sanitized and validated. Malformed hops are safely skipped without throwing errors.
       - The first hop from the right that is NOT in the trusted proxy list is selected as the authentic client IP.
       - If all valid hops in X-Forwarded-For are trusted proxies, returns the leftmost trusted hop.
       - If X-Forwarded-For is missing, empty, or contains only malformed hops, falls back safely to peer_ip.
    """
    if not request.client or not request.client.host:
        return "unknown"

    peer_raw = request.client.host.strip()
    peer_ip = _clean_ip_candidate(peer_raw)
    if not peer_ip:
        return peer_raw or "unknown"

    trusted_nets = parse_trusted_proxies(trusted_proxies)
    if not trusted_nets:
        # No trusted proxies configured; peer is directly authoritative
        return peer_ip

    try:
        peer_addr = ipaddress.ip_address(peer_ip)
    except ValueError:
        return peer_ip

    is_peer_trusted = any(peer_addr in net for net in trusted_nets)
    if not is_peer_trusted:
        # Request arrived directly or from an untrusted peer. Ignore forwarding headers completely.
        return peer_ip

    # Peer is trusted; inspect X-Forwarded-For
    xff_entries = (
        request.headers.getlist("x-forwarded-for")
        if hasattr(request.headers, "getlist")
        else ([request.headers.get("x-forwarded-for")] if request.headers.get("x-forwarded-for") else [])
    )
    if not xff_entries:
        return peer_ip

    # Extract all raw hops across all X-Forwarded-For header entries
    raw_hops: List[str] = []
    for entry in xff_entries:
        if entry and entry.strip():
            raw_hops.extend(h.strip() for h in entry.split(",") if h.strip())

    if not raw_hops:
        return peer_ip

    # Clean and parse valid IP hops
    valid_hops: List[Union[ipaddress.IPv4Address, ipaddress.IPv6Address]] = []
    for h in raw_hops:
        cleaned = _clean_ip_candidate(h)
        if cleaned:
            try:
                valid_hops.append(ipaddress.ip_address(cleaned))
            except ValueError:
                continue

    if not valid_hops:
        # Malformed or unparseable headers fall back safely to peer IP
        return peer_ip

    # Traverse from RIGHT to LEFT to find the first untrusted hop
    for hop_addr in reversed(valid_hops):
        if not any(hop_addr in net for net in trusted_nets):
            return str(hop_addr)

    # All hops in the chain are in the trusted proxy set; return leftmost hop
    return str(valid_hops[0])


from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from backend.app.core.logging import logger
from backend.app.models.audit_event import AuditEvent


class PostgreSQLLoginRateLimiter:
    """
    PostgreSQL-backed login rate limiter utilizing the audit_events table.
    Enforces shared, stateless rate-limiting across distributed API instances
    without introducing external cache dependencies like Redis.
    In production (settings.APP_ENV == "production"), requests fail safely with
    HTTP 503 if the database limiter is unavailable rather than silently falling
    back to process-local state.
    """

    def __init__(self, max_attempts: int = 5, window_seconds: int = 900):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._memory_failures: Dict[str, List[float]] = {}

    def _fail_safe_dependency_unavailable(self, message: str = "Rate limit service is temporarily unavailable. Please try again later.") -> None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": {
                    "code": "DEPENDENCY_UNAVAILABLE",
                    "message": message,
                }
            },
        )

    def is_rate_limited(self, key: str, db: Optional[Session] = None) -> bool:
        if db is None:
            if settings.APP_ENV == "production":
                self._fail_safe_dependency_unavailable()
            now = time.time()
            cutoff = now - self.window_seconds
            attempts = [t for t in self._memory_failures.get(key, []) if t > cutoff]
            self._memory_failures[key] = attempts
            return len(attempts) >= self.max_attempts

        try:
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
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("Rate limiter check failed: %s", exc)
            self._fail_safe_dependency_unavailable()
            return True

    def record_failure(
        self,
        key: str,
        db: Optional[Session] = None,
        email: Optional[str] = None,
        ip: Optional[str] = None,
        user_id: Optional[uuid.UUID] = None,
    ) -> None:
        if db is None:
            if settings.APP_ENV == "production":
                self._fail_safe_dependency_unavailable()
            now = time.time()
            cutoff = now - self.window_seconds
            attempts = [t for t in self._memory_failures.get(key, []) if t > cutoff]
            attempts.append(now)
            self._memory_failures[key] = attempts
            return

        try:
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
        except HTTPException:
            raise
        except Exception as exc:
            db.rollback()
            logger.error("Rate limiter failure record failed: %s", exc)
            self._fail_safe_dependency_unavailable()

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
            if settings.APP_ENV == "production":
                self._fail_safe_dependency_unavailable()
            if key in self._memory_failures:
                del self._memory_failures[key]
            return

        try:
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
        except HTTPException:
            raise
        except Exception as exc:
            db.rollback()
            logger.error("Rate limiter success record failed: %s", exc)
            self._fail_safe_dependency_unavailable()

    def reset(self, key: str, db: Optional[Session] = None) -> None:
        if db is None:
            if settings.APP_ENV == "production":
                self._fail_safe_dependency_unavailable()
            if key in self._memory_failures:
                del self._memory_failures[key]
            return

        try:
            event = AuditEvent(
                event_type="auth.login_success",
                target_type="login_attempt",
                metadata_json={"key": key},
                created_at=datetime.now(timezone.utc),
            )
            db.add(event)
            db.commit()
        except HTTPException:
            raise
        except Exception as exc:
            db.rollback()
            logger.error("Rate limiter reset failed: %s", exc)
            self._fail_safe_dependency_unavailable()


# Alias for backward compatibility
LoginRateLimiter = PostgreSQLLoginRateLimiter

login_rate_limiter = PostgreSQLLoginRateLimiter(
    max_attempts=settings.RATE_LIMIT_LOGIN_MAX_ATTEMPTS,
    window_seconds=settings.RATE_LIMIT_LOGIN_WINDOW_SECONDS,
)
