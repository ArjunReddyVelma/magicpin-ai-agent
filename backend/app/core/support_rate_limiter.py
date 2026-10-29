import hashlib
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple
from fastapi import HTTPException, status
from sqlalchemy import select, func, delete, text
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.models.audit_event import AuditEvent


def derive_advisory_lock_id(key: str) -> int:
    """
    Deterministically maps an arbitrary string key to a 64-bit signed integer
    suitable for PostgreSQL pg_advisory_xact_lock(bigint).
    Uses the first 8 bytes of SHA-256 in big-endian byte order.
    Value is strictly bounded within [-2^63, 2^63 - 1].
    """
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


def _is_postgresql(db: Any) -> bool:
    """Returns True if the SQLAlchemy session is connected to a PostgreSQL engine."""
    if db is None:
        return False
    try:
        bind = getattr(db, "bind", None)
        if bind is not None and hasattr(bind, "dialect"):
            return bind.dialect.name == "postgresql"
        if hasattr(db, "get_bind"):
            bind = db.get_bind()
            if bind is not None and hasattr(bind, "dialect"):
                return bind.dialect.name == "postgresql"
    except Exception:
        pass
    return False


class PublicSupportRateLimiter:
    """
    PostgreSQL-backed rate limiter for public support endpoints using the audit_events table.
    Enforces shared, stateless rate-limiting across distributed API instances with
    transaction-scoped advisory locks and atomic batch commits. Supports an in-memory
    fallback during development/testing.
    """

    def __init__(
        self,
        session_create_limit: int = 10,
        session_create_window: int = 900,  # 15 minutes
        message_ip_limit: int = 20,
        message_ip_window: int = 300,      # 5 minutes
        message_session_limit: int = 10,
        message_session_window: int = 300,  # 5 minutes
        lock_timeout_seconds: float = 3.0,
    ):
        self.session_create_limit = session_create_limit
        self.session_create_window = session_create_window
        self.message_ip_limit = message_ip_limit
        self.message_ip_window = message_ip_window
        self.message_session_limit = message_session_limit
        self.message_session_window = message_session_window
        self.lock_timeout_seconds = lock_timeout_seconds

        self._memory_events: Dict[str, List[float]] = {}
        self._thread_lock = threading.Lock()

    def _fail_safe_dependency_unavailable(
        self,
        message: str = "Rate limit service is temporarily unavailable. Please try again later.",
    ) -> None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": {
                    "code": "DEPENDENCY_UNAVAILABLE",
                    "message": message,
                }
            },
        )

    def _acquire_advisory_locks(self, db: Session, lock_ids: Sequence[int]) -> None:
        """
        Acquires PostgreSQL transaction-scoped advisory locks in strict ascending order.
        Sorted acquisition guarantees mathematical deadlock freedom between concurrent workers.
        Sets a bounded local lock timeout to prevent indefinite hangs.
        Locks are automatically released when the transaction commits or rolls back.
        """
        if not _is_postgresql(db):
            return

        timeout_ms = int(self.lock_timeout_seconds * 1000)
        try:
            db.execute(text(f"SET LOCAL lock_timeout = '{timeout_ms}ms'"))
            for lid in sorted(set(lock_ids)):
                db.execute(text("SELECT pg_advisory_xact_lock(:lid)"), {"lid": lid})
        except Exception as exc:
            db.rollback()
            logger.error("Failed to acquire PostgreSQL advisory lock: %s", exc)
            if settings.APP_ENV == "production":
                self._fail_safe_dependency_unavailable()
            raise

    def _count_events(
        self,
        key: str,
        event_type: str,
        window: int,
        db: Optional[Session],
    ) -> int:
        if db is None:
            now = time.time()
            cutoff = now - window
            return len([t for t in self._memory_events.get(key, []) if t > cutoff])

        now_utc = datetime.now(timezone.utc)
        cutoff_dt = now_utc - timedelta(seconds=window)
        count_stmt = (
            select(func.count(AuditEvent.id))
            .where(
                AuditEvent.event_type == event_type,
                AuditEvent.metadata_json.op("->>")("key") == key,
                AuditEvent.created_at >= cutoff_dt,
            )
        )
        return db.scalar(count_stmt) or 0

    def _is_limited(
        self,
        key: str,
        event_type: str,
        limit: int,
        window: int,
        db: Optional[Session],
    ) -> bool:
        if db is None:
            if settings.APP_ENV == "production":
                self._fail_safe_dependency_unavailable()
            with self._thread_lock:
                now = time.time()
                cutoff = now - window
                timestamps = [t for t in self._memory_events.get(key, []) if t > cutoff]
                self._memory_events[key] = timestamps
                return len(timestamps) >= limit

        try:
            count = self._count_events(key, event_type, window, db)
            return count >= limit
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("Support rate limiter query error: %s", exc)
            if settings.APP_ENV == "production":
                self._fail_safe_dependency_unavailable()
            with self._thread_lock:
                now = time.time()
                cutoff = now - window
                timestamps = [t for t in self._memory_events.get(key, []) if t > cutoff]
                return len(timestamps) >= limit

    def _handle_persistence_failure(self, exc: Exception, db: Optional[Session]) -> None:
        if db is not None:
            try:
                db.rollback()
            except Exception:
                pass
        logger.error("Support rate limiter persistence failure: %s", exc)
        if settings.APP_ENV == "production":
            self._fail_safe_dependency_unavailable()
        elif settings.APP_ENV == "development":
            return
        else:
            raise exc

    def _record_event(
        self,
        key: str,
        event_type: str,
        window: int,
        db: Optional[Session],
        extra_meta: Optional[dict] = None,
    ) -> None:
        with self._thread_lock:
            now = time.time()
            cutoff = now - window
            timestamps = [t for t in self._memory_events.get(key, []) if t > cutoff]
            timestamps.append(now)
            self._memory_events[key] = timestamps

        if db is not None:
            try:
                meta = {"key": key}
                if extra_meta:
                    meta.update(extra_meta)
                event = AuditEvent(
                    user_id=None,
                    merchant_id=None,
                    event_type=event_type,
                    target_type="public_support",
                    metadata_json=meta,
                    created_at=datetime.now(timezone.utc),
                )
                db.add(event)
                db.commit()
            except Exception as exc:
                self._handle_persistence_failure(exc, db)

    def check_session_creation(
        self, client_ip: str, db: Optional[Session] = None
    ) -> None:
        key = f"support_session:{client_ip}"
        if self._is_limited(
            key,
            "support.session_create",
            self.session_create_limit,
            self.session_create_window,
            db,
        ):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": {
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": "Too many session creation requests. Please try again later.",
                    }
                },
            )

    def record_session_creation(
        self, client_ip: str, db: Optional[Session] = None
    ) -> None:
        key = f"support_session:{client_ip}"
        event_type = "support.session_create"
        window = self.session_create_window
        limit = self.session_create_limit

        if db is not None:
            try:
                # 1. Acquire advisory lock deterministically
                lock_id = derive_advisory_lock_id(key)
                self._acquire_advisory_locks(db, [lock_id])

                # 2. Concurrency-safe recheck inside protected transaction
                count = self._count_events(key, event_type, window, db)
                if count >= limit:
                    db.rollback()
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={
                            "error": {
                                "code": "RATE_LIMIT_EXCEEDED",
                                "message": "Too many session creation requests. Please try again later.",
                            }
                        },
                    )

                # 3. Insert and commit
                event = AuditEvent(
                    user_id=None,
                    merchant_id=None,
                    event_type=event_type,
                    target_type="public_support",
                    metadata_json={"key": key, "ip": client_ip},
                    created_at=datetime.now(timezone.utc),
                )
                db.add(event)
                db.commit()
            except HTTPException:
                raise
            except Exception as exc:
                self._handle_persistence_failure(exc, db)
                with self._thread_lock:
                    now = time.time()
                    cutoff = now - window
                    timestamps = [t for t in self._memory_events.get(key, []) if t > cutoff]
                    if len(timestamps) >= limit:
                        raise HTTPException(
                            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail={
                                "error": {
                                    "code": "RATE_LIMIT_EXCEEDED",
                                    "message": "Too many session creation requests. Please try again later.",
                                }
                            },
                        )
                    timestamps.append(now)
                    self._memory_events[key] = timestamps
        else:
            if settings.APP_ENV == "production":
                self._fail_safe_dependency_unavailable()
            with self._thread_lock:
                now = time.time()
                cutoff = now - window
                timestamps = [t for t in self._memory_events.get(key, []) if t > cutoff]
                if len(timestamps) >= limit:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={
                            "error": {
                                "code": "RATE_LIMIT_EXCEEDED",
                                "message": "Too many session creation requests. Please try again later.",
                            }
                        },
                    )
                timestamps.append(now)
                self._memory_events[key] = timestamps

    def check_message_submission(
        self, client_ip: str, session_id: uuid.UUID, db: Optional[Session] = None
    ) -> None:
        ip_key = f"support_msg_ip:{client_ip}"
        session_key = f"support_msg_session:{session_id}"

        if self._is_limited(
            ip_key,
            "support.message_submit_ip",
            self.message_ip_limit,
            self.message_ip_window,
            db,
        ):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": {
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": "Too many messages sent from this IP address. Please wait a few minutes.",
                    }
                },
            )

        if self._is_limited(
            session_key,
            "support.message_submit_session",
            self.message_session_limit,
            self.message_session_window,
            db,
        ):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": {
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": "Too many messages sent in this session. Please wait a few minutes.",
                    }
                },
            )

    def record_message_submission(
        self, client_ip: str, session_id: uuid.UUID, db: Optional[Session] = None
    ) -> None:
        ip_key = f"support_msg_ip:{client_ip}"
        session_key = f"support_msg_session:{session_id}"
        ip_limit = self.message_ip_limit
        ip_window = self.message_ip_window
        session_limit = self.message_session_limit
        session_window = self.message_session_window

        if db is not None:
            try:
                # 1. Deterministic advisory locks: sorted order prevents deadlocks
                ip_lock_id = derive_advisory_lock_id(ip_key)
                session_lock_id = derive_advisory_lock_id(session_key)
                self._acquire_advisory_locks(db, [ip_lock_id, session_lock_id])

                # 2. Concurrency re-checks inside protected transaction
                ip_count = self._count_events(ip_key, "support.message_submit_ip", ip_window, db)
                if ip_count >= ip_limit:
                    db.rollback()
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={
                            "error": {
                                "code": "RATE_LIMIT_EXCEEDED",
                                "message": "Too many messages sent from this IP address. Please wait a few minutes.",
                            }
                        },
                    )

                session_count = self._count_events(
                    session_key, "support.message_submit_session", session_window, db
                )
                if session_count >= session_limit:
                    db.rollback()
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={
                            "error": {
                                "code": "RATE_LIMIT_EXCEEDED",
                                "message": "Too many messages sent in this session. Please wait a few minutes.",
                            }
                        },
                    )

                # 3. Single atomic batch insert of both events
                now_utc = datetime.now(timezone.utc)
                ip_event = AuditEvent(
                    user_id=None,
                    merchant_id=None,
                    event_type="support.message_submit_ip",
                    target_type="public_support",
                    metadata_json={"key": ip_key, "ip": client_ip, "session_id": str(session_id)},
                    created_at=now_utc,
                )
                session_event = AuditEvent(
                    user_id=None,
                    merchant_id=None,
                    event_type="support.message_submit_session",
                    target_type="public_support",
                    metadata_json={"key": session_key, "session_id": str(session_id)},
                    created_at=now_utc,
                )

                db.add_all([ip_event, session_event])
                db.commit()

            except HTTPException:
                raise
            except Exception as exc:
                self._handle_persistence_failure(exc, db)
                with self._thread_lock:
                    now = time.time()
                    ip_cutoff = now - ip_window
                    sess_cutoff = now - session_window
                    ip_ts = [t for t in self._memory_events.get(ip_key, []) if t > ip_cutoff]
                    sess_ts = [t for t in self._memory_events.get(session_key, []) if t > sess_cutoff]
                    if len(ip_ts) >= ip_limit:
                        raise HTTPException(
                            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail={
                                "error": {
                                    "code": "RATE_LIMIT_EXCEEDED",
                                    "message": "Too many messages sent from this IP address. Please wait a few minutes.",
                                }
                            },
                        )
                    if len(sess_ts) >= session_limit:
                        raise HTTPException(
                            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail={
                                "error": {
                                    "code": "RATE_LIMIT_EXCEEDED",
                                    "message": "Too many messages sent in this session. Please wait a few minutes.",
                                }
                            },
                        )
                    ip_ts.append(now)
                    sess_ts.append(now)
                    self._memory_events[ip_key] = ip_ts
                    self._memory_events[session_key] = sess_ts
        else:
            if settings.APP_ENV == "production":
                self._fail_safe_dependency_unavailable()
            with self._thread_lock:
                now = time.time()
                ip_cutoff = now - ip_window
                sess_cutoff = now - session_window
                ip_ts = [t for t in self._memory_events.get(ip_key, []) if t > ip_cutoff]
                sess_ts = [t for t in self._memory_events.get(session_key, []) if t > sess_cutoff]
                if len(ip_ts) >= ip_limit:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={
                            "error": {
                                "code": "RATE_LIMIT_EXCEEDED",
                                "message": "Too many messages sent from this IP address. Please wait a few minutes.",
                            }
                        },
                    )
                if len(sess_ts) >= session_limit:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={
                            "error": {
                                "code": "RATE_LIMIT_EXCEEDED",
                                "message": "Too many messages sent in this session. Please wait a few minutes.",
                            }
                        },
                    )
                ip_ts.append(now)
                sess_ts.append(now)
                self._memory_events[ip_key] = ip_ts
                self._memory_events[session_key] = sess_ts

    def reset(self) -> None:
        """Reset memory store (primarily for unit tests)."""
        with self._thread_lock:
            self._memory_events.clear()


support_rate_limiter = PublicSupportRateLimiter()

# Explicit tuple of disposable ephemeral rate-limiting event types.
# Ordinary audit/security logs (e.g. auth.login_*, action.*, merchant.*) are strictly excluded.
DISPOSABLE_SUPPORT_EVENT_TYPES = (
    "support.session_create",
    "support.message_submit_ip",
    "support.message_submit_session",
)


def prune_expired_support_rate_limit_events(
    db: Session,
    max_age_hours: int = 24,
    batch_size: int = 1000,
    max_batches: int = 50,
) -> int:
    """
    Safely prunes expired ephemeral public-support rate-limit events.

    Safety & boundary rules:
    1. STRICTLY RESTRICTED to target_type == 'public_support' and event_type in DISPOSABLE_SUPPORT_EVENT_TYPES.
    2. Ordinary security and audit events (auth.login_success, auth.login_failure,
       merchant mutations, suggested actions) are NEVER eligible for deletion.
    3. Records with user_id IS NOT NULL or merchant_id IS NOT NULL are NEVER deleted.
    4. Only records older than max_age_hours (default 24h, well beyond the 5-15 min rate-limit windows)
       are eligible.
    5. Bounded batch execution: deletes in batches of batch_size (default 1000) up to max_batches
       to prevent lock contention, transaction log bloat, or table-level exclusive locks.
    6. Commits per batch so progress is incremental and safely retryable upon interruption.
    Returns the total count of pruned records.
    """
    if max_age_hours < 1:
        raise ValueError("max_age_hours must be at least 1 hour to protect active rate-limit windows.")

    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    total_deleted = 0

    for _ in range(max_batches):
        candidate_subquery = (
            select(AuditEvent.id)
            .where(
                AuditEvent.target_type == "public_support",
                AuditEvent.event_type.in_(DISPOSABLE_SUPPORT_EVENT_TYPES),
                AuditEvent.user_id.is_(None),
                AuditEvent.merchant_id.is_(None),
                AuditEvent.created_at < cutoff,
            )
            .limit(batch_size)
            .scalar_subquery()
        )

        delete_stmt = (
            delete(AuditEvent)
            .where(AuditEvent.id.in_(candidate_subquery))
            .execution_options(synchronize_session=False)
        )

        result = db.execute(delete_stmt)
        deleted_in_batch = result.rowcount
        db.commit()

        total_deleted += deleted_in_batch
        if deleted_in_batch < batch_size:
            break

    logger.info("Pruned %d expired public-support rate-limit events (cutoff: %s)", total_deleted, cutoff)
    return total_deleted
