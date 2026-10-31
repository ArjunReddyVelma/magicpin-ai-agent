"""
Integration and regression tests for PERF-01:
Rate-limiting index optimization and ephemeral retention boundaries.

Verifies:
1. Index creation on (event_type, metadata_json->>'key', created_at).
2. PostgreSQL query plan uses ix_audit_events_rate_limiting instead of sequential scan.
3. Retention pruning deletes ONLY expired ephemeral public support records (target_type='public_support').
4. Compliance & security audit trails (auth.login_*, records with merchant_id/user_id) are strictly preserved.
5. Migration downgrade and re-upgrade cycles cleanly on the isolated test database.
"""
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import create_engine, inspect, text, select
from sqlalchemy.orm import Session

from alembic.config import Config
from alembic import command

from backend.app.core.config import settings
from backend.app.core.db_safety import validate_test_database_isolation
from backend.app.db.session import check_database_connection
from backend.app.core.support_rate_limiter import (
    prune_expired_support_rate_limit_events,
    DISPOSABLE_SUPPORT_EVENT_TYPES,
)
from backend.app.models.audit_event import AuditEvent
from backend.app.models.merchant_profile import MerchantProfile
from backend.app.models.user import User


def test_index_exists_and_query_planner_uses_index(db_session: Session):
    """
    Verifies that ix_audit_events_rate_limiting exists in PostgreSQL and
    that the rate-limiting query pattern utilizes index scanning.
    """
    validate_test_database_isolation()

    # Seed sample records so PostgreSQL planner considers index scan
    now_utc = datetime.now(timezone.utc)
    for i in range(100):
        db_session.add(
            AuditEvent(
                user_id=None,
                merchant_id=None,
                event_type="support.session_create",
                target_type="public_support",
                metadata_json={"key": f"support_session:10.0.0.{i}"},
                created_at=now_utc - timedelta(minutes=i),
            )
        )
    db_session.flush()

    # Inspect index names on audit_events
    engine = db_session.get_bind()
    inspector = inspect(engine)
    indexes = inspector.get_indexes("audit_events")
    index_names = {idx["name"] for idx in indexes}
    assert "ix_audit_events_rate_limiting" in index_names, (
        f"Missing ix_audit_events_rate_limiting in {index_names}"
    )

    # Run EXPLAIN with enable_seqscan=off to verify index viability
    db_session.execute(text("SET LOCAL enable_seqscan = off;"))
    plan_rows = db_session.execute(
        text(
            """
            EXPLAIN
            SELECT count(id)
            FROM audit_events
            WHERE event_type = 'support.session_create'
              AND (metadata_json ->> 'key') = 'support_session:10.0.0.1'
              AND created_at >= NOW() - INTERVAL '15 minutes';
            """
        )
    ).fetchall()
    plan_text = "\n".join(row[0] for row in plan_rows)

    assert "ix_audit_events_rate_limiting" in plan_text, (
        f"Query plan did not reference ix_audit_events_rate_limiting:\n{plan_text}"
    )
    assert ("Index Scan" in plan_text or "Bitmap Index Scan" in plan_text), (
        f"Expected index scan in query plan:\n{plan_text}"
    )


def test_ephemeral_retention_pruning_boundary_strictness(
    db_session: Session,
    test_merchant: MerchantProfile,
    test_user: User,
):
    """
    CRITICAL RETENTION TEST:
    Verifies that prune_expired_support_rate_limit_events ONLY deletes expired
    ephemeral public support records and NEVER touches security/compliance audit trails.
    """
    now_utc = datetime.now(timezone.utc)
    old_time = now_utc - timedelta(hours=48)  # 48 hours old (> 24h threshold)
    recent_time = now_utc - timedelta(minutes=10)  # 10 minutes old (< 24h threshold)

    # 1. Ephemeral public support events (OLD -> ELIGIBLE)
    eph_old_1 = AuditEvent(
        user_id=None,
        merchant_id=None,
        event_type="support.session_create",
        target_type="public_support",
        metadata_json={"key": "support_session:1.1.1.1"},
        created_at=old_time,
    )
    eph_old_2 = AuditEvent(
        user_id=None,
        merchant_id=None,
        event_type="support.message_submit_ip",
        target_type="public_support",
        metadata_json={"key": "support_msg_ip:1.1.1.1"},
        created_at=old_time,
    )
    eph_old_3 = AuditEvent(
        user_id=None,
        merchant_id=None,
        event_type="support.message_submit_session",
        target_type="public_support",
        metadata_json={"key": "support_msg_session:uuid"},
        created_at=old_time,
    )

    # 2. Ephemeral public support events (RECENT -> MUST BE RETAINED)
    eph_recent = AuditEvent(
        user_id=None,
        merchant_id=None,
        event_type="support.session_create",
        target_type="public_support",
        metadata_json={"key": "support_session:2.2.2.2"},
        created_at=recent_time,
    )

    # 3. Security audit event: auth.login_failure (OLD -> MUST BE RETAINED)
    sec_old_fail = AuditEvent(
        user_id=None,
        merchant_id=None,
        event_type="auth.login_failure",
        target_type="login_attempt",
        metadata_json={"key": "127.0.0.1:target@example.com"},
        created_at=old_time,
    )

    # 4. Security audit event: auth.login_success (OLD -> MUST BE RETAINED)
    sec_old_success = AuditEvent(
        user_id=test_user.id,
        merchant_id=test_merchant.id,
        event_type="auth.login_success",
        target_type="login_attempt",
        metadata_json={"key": "127.0.0.1:target@example.com"},
        created_at=old_time,
    )

    # 5. Merchant-owned audit event (OLD -> MUST BE RETAINED)
    merchant_audit = AuditEvent(
        user_id=test_user.id,
        merchant_id=test_merchant.id,
        event_type="context.created",
        target_type="context_item",
        metadata_json={"title": "Policy Document"},
        created_at=old_time,
    )

    # 6. Ephemeral event type with merchant_id attached (OLD -> MUST BE RETAINED due to merchant link)
    eph_with_merchant = AuditEvent(
        user_id=None,
        merchant_id=test_merchant.id,
        event_type="support.session_create",
        target_type="public_support",
        metadata_json={"key": "support_session:3.3.3.3"},
        created_at=old_time,
    )

    records = [
        eph_old_1,
        eph_old_2,
        eph_old_3,
        eph_recent,
        sec_old_fail,
        sec_old_success,
        merchant_audit,
        eph_with_merchant,
    ]
    db_session.add_all(records)
    db_session.flush()

    # Track IDs
    eligible_ids = {eph_old_1.id, eph_old_2.id, eph_old_3.id}
    retained_ids = {
        eph_recent.id,
        sec_old_fail.id,
        sec_old_success.id,
        merchant_audit.id,
        eph_with_merchant.id,
    }

    # Run pruning routine with max_age_hours=24
    pruned_count = prune_expired_support_rate_limit_events(
        db=db_session,
        max_age_hours=24,
        batch_size=10,
    )
    assert pruned_count >= 3, f"Expected at least 3 pruned records, got {pruned_count}"

    # Verify database state after pruning
    remaining_records = db_session.execute(
        select(AuditEvent.id).where(AuditEvent.id.in_(eligible_ids | retained_ids))
    ).scalars().all()
    remaining_id_set = set(remaining_records)

    # Assert eligible records were deleted
    for eid in eligible_ids:
        assert eid not in remaining_id_set, f"Eligible ephemeral record {eid} was not deleted"

    # Assert all protected and recent records are STILL PRESENT
    for rid in retained_ids:
        assert rid in remaining_id_set, f"Protected audit record {rid} was mistakenly deleted!"


def test_pruning_idempotent_and_safe_on_empty(db_session: Session):
    """Verifies pruning returns 0 cleanly when no eligible records exist."""
    count = prune_expired_support_rate_limit_events(db=db_session, max_age_hours=24)
    assert count == 0


def test_pruning_rejects_unsafe_small_age_window(db_session: Session):
    """Verifies that max_age_hours < 1 raises ValueError to protect active windows."""
    with pytest.raises(ValueError, match="max_age_hours must be at least 1 hour"):
        prune_expired_support_rate_limit_events(db=db_session, max_age_hours=0)


def test_pruning_batch_limits(db_session: Session):
    """Verifies that pruning enforces batch_size and max_batches limits."""
    validate_test_database_isolation()
    now_utc = datetime.now(timezone.utc)
    old_time = now_utc - timedelta(hours=48)

    # Seed 5 old eligible records
    records = [
        AuditEvent(
            user_id=None,
            merchant_id=None,
            event_type="support.session_create",
            target_type="public_support",
            metadata_json={"key": f"batch_test:{uuid.uuid4().hex[:6]}"},
            created_at=old_time,
        )
        for _ in range(5)
    ]
    db_session.add_all(records)
    db_session.flush()

    # Bounded execution: batch_size=2, max_batches=2 -> deletes at most 4
    deleted = prune_expired_support_rate_limit_events(
        db=db_session,
        max_age_hours=24,
        batch_size=2,
        max_batches=2,
    )
    assert deleted == 4, f"Expected 4 deleted records across 2 batches, got {deleted}"

    # Final run cleans up the remaining record
    deleted_remaining = prune_expired_support_rate_limit_events(
        db=db_session,
        max_age_hours=24,
        batch_size=10,
    )
    assert deleted_remaining >= 1


def test_prune_script_dry_run_cli(db_session: Session):
    """Verifies that running scripts/prune_rate_limit_events.py in dry-run mode does not delete records."""
    validate_test_database_isolation()
    now_utc = datetime.now(timezone.utc)
    old_time = now_utc - timedelta(hours=48)

    sample_event = AuditEvent(
        user_id=None,
        merchant_id=None,
        event_type="support.session_create",
        target_type="public_support",
        metadata_json={"key": f"cli_test:{uuid.uuid4().hex[:6]}"},
        created_at=old_time,
    )
    db_session.add(sample_event)
    db_session.commit()
    sample_id = sample_event.id

    # Execute script CLI in dry-run mode against isolated test database
    cmd = [
        sys.executable,
        "scripts/prune_rate_limit_events.py",
        "--db-url",
        settings.DATABASE_URL_TEST,
        "--max-age-hours",
        "24",
        "--dry-run",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    assert "Dry run complete. No records were deleted." in res.stdout

    # Verify the record still exists in the database
    exists = db_session.execute(
        select(AuditEvent.id).where(AuditEvent.id == sample_id)
    ).scalar_one_or_none()
    assert exists is not None, "Dry run mistakenly deleted the record!"

    # Clean up test record
    prune_expired_support_rate_limit_events(db=db_session, max_age_hours=24)


def test_migration_0004_downgrade_and_reupgrade_cycle():
    """
    Verifies that migration 0004 can be rolled back safely (-1) and re-applied
    on the isolated test database without running downgrade base.
    """
    test_db_url = settings.DATABASE_URL_TEST
    validate_test_database_isolation(test_db_url)

    engine = create_engine(test_db_url)
    if not check_database_connection(engine):
        engine.dispose()
        pytest.skip("Test database (DATABASE_URL_TEST) is unavailable; skipping migration test.")

    alembic_cfg = Config("backend/alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", test_db_url)
    alembic_cfg.set_main_option("script_location", "backend/migrations")

    # 1. Upgrade to 0004_rate_limit_optimization to test its specific rollback
    command.upgrade(alembic_cfg, "0004_rate_limit_optimization")
    inspector = inspect(engine)
    indexes = {idx["name"] for idx in inspector.get_indexes("audit_events")}
    assert "ix_audit_events_rate_limiting" in indexes

    # 2. Downgrade -1 (rolls back 0004 to 0003)
    command.downgrade(alembic_cfg, "-1")
    inspector = inspect(engine)
    remaining_indexes = {idx["name"] for idx in inspector.get_indexes("audit_events")}
    assert "ix_audit_events_rate_limiting" not in remaining_indexes, (
        "ix_audit_events_rate_limiting should have been dropped by downgrade -1"
    )
    # Underlying tables and indexes must remain intact
    assert "ix_audit_events_merchant_created" in remaining_indexes

    # 3. Re-upgrade to head
    command.upgrade(alembic_cfg, "head")
    inspector = inspect(engine)
    recreated_indexes = {idx["name"] for idx in inspector.get_indexes("audit_events")}
    assert "ix_audit_events_rate_limiting" in recreated_indexes

    engine.dispose()
