"""
Maintenance script: Prunes expired ephemeral public-support rate-limit events.

Usage:
    python scripts/prune_rate_limit_events.py [--max-age-hours 24] [--batch-size 1000]

Safety guarantees:
- Operates strictly on ephemeral support rate-limiting events (target_type == 'public_support').
- Ordinary security/audit records (auth.login_*, action.*, merchant.*) are strictly preserved.
"""
import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Ensure repository root is in sys.path when invoked directly as a script
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import select, func, create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.db.session import SessionLocal
from backend.app.models.audit_event import AuditEvent
from backend.app.core.support_rate_limiter import (
    prune_expired_support_rate_limit_events,
    DISPOSABLE_SUPPORT_EVENT_TYPES,
)


def main():
    parser = argparse.ArgumentParser(
        description="Prune expired ephemeral public-support rate-limit events from audit_events."
    )
    parser.add_argument(
        "--max-age-hours",
        type=int,
        default=24,
        help="Prune ephemeral rate-limit events older than this many hours (minimum 1, default 24).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="Number of records to delete per committed batch (default 1000).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count eligible records without deleting.",
    )
    parser.add_argument(
        "--db-url",
        type=str,
        default=None,
        help="Database connection URL (defaults to settings.DATABASE_URL).",
    )
    args = parser.parse_args()

    if args.max_age_hours < 1:
        print("ERROR: --max-age-hours must be at least 1.", file=sys.stderr)
        sys.exit(1)

    custom_engine = None
    if args.db_url:
        custom_engine = create_engine(args.db_url, pool_pre_ping=True)
        session_factory = sessionmaker(autocommit=False, autoflush=False, bind=custom_engine)
        db = session_factory()
    else:
        db = SessionLocal()

    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=args.max_age_hours)
        count_stmt = (
            select(func.count(AuditEvent.id))
            .where(
                AuditEvent.target_type == "public_support",
                AuditEvent.event_type.in_(DISPOSABLE_SUPPORT_EVENT_TYPES),
                AuditEvent.user_id.is_(None),
                AuditEvent.merchant_id.is_(None),
                AuditEvent.created_at < cutoff,
            )
        )
        eligible_count = db.scalar(count_stmt) or 0

        print(f"Eligible ephemeral rate-limit events older than {args.max_age_hours}h (before {cutoff}): {eligible_count}")

        if args.dry_run:
            print("Dry run complete. No records were deleted.")
            return

        if eligible_count == 0:
            print("No records eligible for pruning.")
            return

        deleted = prune_expired_support_rate_limit_events(
            db=db,
            max_age_hours=args.max_age_hours,
            batch_size=args.batch_size,
        )
        print(f"SUCCESS: Pruned {deleted} expired rate-limit records.")
    finally:
        db.close()
        if custom_engine:
            custom_engine.dispose()


if __name__ == "__main__":
    main()
