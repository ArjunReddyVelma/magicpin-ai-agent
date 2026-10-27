import os
import pytest
from alembic.config import Config
from alembic import command
from sqlalchemy import create_engine, inspect

from backend.app.core.config import settings
from backend.app.core.db_safety import validate_test_database_isolation
from backend.app.db.session import check_database_connection


def test_alembic_upgrade_downgrade_cycle():
    """
    Verifies that Alembic can apply migrations up to head,
    safely roll back the latest revision, and re-apply cleanly on the confirmed test database.
    Does NOT wipe the entire database to base.
    """
    test_db_url = settings.DATABASE_URL_TEST

    # Fail-closed validation before any migration command
    validate_test_database_isolation(test_db_url)

    engine = create_engine(test_db_url)
    if not check_database_connection(engine):
        engine.dispose()
        pytest.skip("Test database (DATABASE_URL_TEST) is unavailable; skipping migration test.")

    alembic_cfg = Config("backend/alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", test_db_url)
    alembic_cfg.set_main_option("script_location", "backend/migrations")

    # 1. Upgrade to head
    command.upgrade(alembic_cfg, "head")

    inspector = inspect(engine)
    tables = inspector.get_table_names()

    expected_tables = {
        "users",
        "merchant_profiles",
        "user_sessions",
        "context_items",
        "conversations",
        "messages",
        "suggested_actions",
        "audit_events",
        "whatsapp_accounts",
        "whatsapp_messages",
        "customer_support_sessions",
        "customer_support_messages",
        "alembic_version",
    }
    assert expected_tables.issubset(set(tables)), f"Missing tables in {tables}"

    # 2. Safely test downgrade of the head revision (-1 rolls back 0004 index)
    command.downgrade(alembic_cfg, "-1")
    inspector = inspect(engine)
    remaining_indexes = {idx["name"] for idx in inspector.get_indexes("audit_events")}
    assert "ix_audit_events_rate_limiting" not in remaining_indexes, (
        "Head migration index ix_audit_events_rate_limiting was not dropped by downgrade -1"
    )
    # Tables from 0003 should still be intact
    tables_after_idx_drop = set(inspector.get_table_names())
    assert expected_tables.issubset(tables_after_idx_drop), "Tables unexpectedly modified by index rollback"

    # 3. Test downgrade of 0003 (down another revision to 0002)
    command.downgrade(alembic_cfg, "-1")
    inspector = inspect(engine)
    tables_after_0003_drop = set(inspector.get_table_names())
    support_tables = {"customer_support_sessions", "customer_support_messages"}
    assert not support_tables.intersection(tables_after_0003_drop), (
        f"0003 support tables {support_tables} were not dropped by downgrade"
    )
    # Base tables should still be intact
    base_tables = {"users", "merchant_profiles", "user_sessions"}
    assert base_tables.issubset(tables_after_0003_drop), "Base tables were unexpectedly affected"

    # 4. Re-upgrade to head
    command.upgrade(alembic_cfg, "head")
    inspector = inspect(engine)
    recreated_tables = set(inspector.get_table_names())
    assert expected_tables.issubset(recreated_tables), "Re-created tables missing after upgrade head"
    recreated_indexes = {idx["name"] for idx in inspector.get_indexes("audit_events")}
    assert "ix_audit_events_rate_limiting" in recreated_indexes, "Re-created index missing after upgrade head"
    engine.dispose()
