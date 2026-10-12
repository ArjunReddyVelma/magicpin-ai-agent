import os
from alembic.config import Config
from alembic import command
from sqlalchemy import create_engine, inspect

from backend.app.core.config import settings


def test_alembic_upgrade_downgrade_cycle():
    """
    Verifies that Alembic can apply migrations up to head,
    roll back to base, and re-apply cleanly on the test database.
    """
    test_db_url = settings.DATABASE_URL_TEST

    alembic_cfg = Config("backend/alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", test_db_url)
    alembic_cfg.set_main_option("script_location", "backend/migrations")

    # 1. Downgrade to base first in case tables exist
    try:
        command.downgrade(alembic_cfg, "base")
    except Exception:
        pass

    # 2. Upgrade to head
    command.upgrade(alembic_cfg, "head")

    engine = create_engine(test_db_url)
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
        "alembic_version",
    }
    assert expected_tables.issubset(set(tables)), f"Missing tables in {tables}"

    # 3. Downgrade to base
    command.downgrade(alembic_cfg, "base")
    inspector = inspect(engine)
    remaining_tables = set(inspector.get_table_names())
    # All app tables should be dropped (alembic_version may remain)
    app_tables = expected_tables - {"alembic_version"}
    assert not app_tables.intersection(remaining_tables), "Tables were not dropped"

    # 4. Re-upgrade to head
    command.upgrade(alembic_cfg, "head")
    inspector = inspect(engine)
    recreated_tables = set(inspector.get_table_names())
    assert expected_tables.issubset(recreated_tables), "Re-created tables missing"
    engine.dispose()
