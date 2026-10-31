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

    # 1. Upgrade to head (0005)
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
        "customer_support_sessions",
        "customer_support_messages",
        "alembic_version",
    }
    assert expected_tables.issubset(set(tables)), f"Missing tables in {tables}"
    removed_tables = {"whatsapp_accounts", "whatsapp_messages"}
    assert not removed_tables.intersection(set(tables)), (
        f"WhatsApp tables {removed_tables} were not dropped by head migration"
    )

    # 2. Safely test downgrade of the head revision (-1 rolls back 0005, restoring WhatsApp tables in 0004)
    command.downgrade(alembic_cfg, "-1")
    inspector = inspect(engine)
    tables_after_0005_rollback = set(inspector.get_table_names())
    assert removed_tables.issubset(tables_after_0005_rollback), (
        "Downgrade of 0005 did not restore WhatsApp tables"
    )

    # 3. Safely test downgrade of 0004 (-1 rolls back 0004 index)
    command.downgrade(alembic_cfg, "-1")
    inspector = inspect(engine)
    remaining_indexes = {idx["name"] for idx in inspector.get_indexes("audit_events")}
    assert "ix_audit_events_rate_limiting" not in remaining_indexes, (
        "Migration index ix_audit_events_rate_limiting was not dropped by downgrade"
    )

    # 4. Test downgrade of 0003 (down another revision to 0002)
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

    # 5. Re-upgrade to head (0005)
    command.upgrade(alembic_cfg, "head")
    inspector = inspect(engine)
    recreated_tables = set(inspector.get_table_names())
    assert expected_tables.issubset(recreated_tables), "Re-created tables missing after upgrade head"
    assert not removed_tables.intersection(recreated_tables), "WhatsApp tables unexpectedly exist at head"
    recreated_indexes = {idx["name"] for idx in inspector.get_indexes("audit_events")}
    assert "ix_audit_events_rate_limiting" in recreated_indexes, "Re-created index missing after upgrade head"
    engine.dispose()
