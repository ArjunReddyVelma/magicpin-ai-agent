import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from fastapi import HTTPException, status
from sqlalchemy import select, func, delete
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.models.audit_event import AuditEvent


class PublicSupportRateLimiter:
    """
    PostgreSQL-backed rate limiter for public support endpoints using the audit_events table.
    Enforces shared, stateless rate-limiting across distributed API instances without
    external cache dependencies. Supports an in-memory fallback during development/testing.
    """

    def __init__(
        self,
        session_create_limit: int = 10,
        session_create_window: int = 900,  # 15 minutes
        message_ip_limit: int = 20,
        message_ip_window: int = 300,      # 5 minutes
        message_session_limit: int = 10,
        message_session_window: int = 300,  # 5 minutes
    ):
        self.session_create_limit = session_create_limit
        self.session_create_window = session_create_window
        self.message_ip_limit = message_ip_limit
        self.message_ip_window = message_ip_window
        self.message_session_limit = message_session_limit
        self.message_session_window = message_session_window

        self._memory_events: Dict[str, List[float]] = {}

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
            now = time.time()
            cutoff = now - window
            timestamps = [t for t in self._memory_events.get(key, []) if t > cutoff]
            self._memory_events[key] = timestamps
            return len(timestamps) >= limit

        try:
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
            count = db.scalar(count_stmt) or 0
            return count >= limit
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("Support rate limiter query error: %s", exc)
            if settings.APP_ENV == "production":
                self._fail_safe_dependency_unavailable()
            now = time.time()
            cutoff = now - window
            timestamps = [t for t in self._memory_events.get(key, []) if t > cutoff]
            return len(timestamps) >= limit

    def _record_event(
        self,
        key: str,
        event_type: str,
        window: int,
        db: Optional[Session],
        extra_meta: Optional[dict] = None,
    ) -> None:
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
                db.rollback()
                logger.error("Support rate limiter record event error: %s", exc)

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
        self._record_event(
            key,
            "support.session_create",
            self.session_create_window,
            db,
            {"ip": client_ip},
        )

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
        self._record_event(
            ip_key,
            "support.message_submit_ip",
            self.message_ip_window,
            db,
            {"ip": client_ip, "session_id": str(session_id)},
        )
        self._record_event(
            session_key,
            "support.message_submit_session",
            self.message_session_window,
            db,
            {"session_id": str(session_id)},
        )

    def reset(self) -> None:
        """Reset memory store (primarily for unit tests)."""
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
