"""
Unit tests for database isolation safeguards (REL-01).

Validates that fail-closed checks prevent any execution against primary,
production, or unverified remote databases.
"""
import pytest
from backend.app.core.db_safety import (
    validate_test_database_isolation,
    DatabaseIsolationError,
)


def test_valid_test_configuration_passes():
    """Confirms properly configured local test URL passes validation."""
    validate_test_database_isolation(
        test_url="postgresql+psycopg://reddy@localhost:5432/magicpin_ai_agent_test",
        primary_url="postgresql+psycopg://reddy@localhost:5432/magicpin_ai_agent",
        app_env="development",
    )


def test_valid_loopback_ip_passes():
    """Confirms 127.0.0.1 test URL passes validation."""
    validate_test_database_isolation(
        test_url="postgresql+psycopg://user:pass@127.0.0.1:5432/custom_app_test",
        primary_url="postgresql+psycopg://user:pass@127.0.0.1:5432/custom_app",
        app_env="test",
    )


def test_production_environment_fails():
    """Confirms validation raises DatabaseIsolationError if APP_ENV is production."""
    with pytest.raises(DatabaseIsolationError, match="Tests cannot run in production"):
        validate_test_database_isolation(
            test_url="postgresql+psycopg://reddy@localhost:5432/magicpin_ai_agent_test",
            primary_url="postgresql+psycopg://reddy@localhost:5432/magicpin_ai_agent",
            app_env="production",
        )


def test_matching_urls_fails():
    """Confirms validation raises DatabaseIsolationError if test URL equals primary URL."""
    url = "postgresql+psycopg://reddy@localhost:5432/magicpin_ai_agent_test"
    with pytest.raises(DatabaseIsolationError, match="matches primary database URL"):
        validate_test_database_isolation(
            test_url=url,
            primary_url=url,
            app_env="development",
        )


def test_targeting_protected_primary_db_name_fails():
    """Confirms validation raises DatabaseIsolationError if test database is magicpin_ai_agent."""
    with pytest.raises(DatabaseIsolationError, match="protected database 'magicpin_ai_agent'"):
        validate_test_database_isolation(
            test_url="postgresql+psycopg://user@localhost:5433/magicpin_ai_agent",
            primary_url="postgresql+psycopg://user@localhost:5432/primary_app_db",
            app_env="development",
        )


def test_targeting_same_db_name_fails():
    """Confirms validation raises DatabaseIsolationError if test database name equals primary."""
    with pytest.raises(DatabaseIsolationError, match="equals primary database name"):
        validate_test_database_isolation(
            test_url="postgresql+psycopg://user@localhost:5433/custom_db_test",
            primary_url="postgresql+psycopg://user@localhost:5432/custom_db_test",
            app_env="development",
        )


def test_database_name_without_test_suffix_fails():
    """Confirms database name must explicitly end with _test."""
    with pytest.raises(DatabaseIsolationError, match="must end with '_test'"):
        validate_test_database_isolation(
            test_url="postgresql+psycopg://user@localhost:5432/testing_database",
            primary_url="postgresql+psycopg://user@localhost:5432/magicpin_ai_agent",
            app_env="development",
        )


def test_test_name_with_production_marker_fails():
    """Confirms a name containing 'prod' or 'live' fails even if it ends with _test."""
    with pytest.raises(DatabaseIsolationError, match="forbidden production marker"):
        validate_test_database_isolation(
            test_url="postgresql+psycopg://user@localhost:5432/production_replica_test",
            primary_url="postgresql+psycopg://user@localhost:5432/magicpin_ai_agent",
            app_env="development",
        )


def test_remote_cloud_host_fails_even_if_name_contains_test():
    """Confirms remote cloud hosts fail even if database name ends with _test."""
    with pytest.raises(DatabaseIsolationError, match="matches remote cloud host marker"):
        validate_test_database_isolation(
            test_url="postgresql+psycopg://user:pass@dpg-xxx.oregon-postgres.render.com:5432/app_test",
            primary_url="postgresql+psycopg://user:pass@localhost:5432/app",
            app_env="development",
        )


def test_non_loopback_ip_fails():
    """Confirms public or external IP addresses fail validation."""
    with pytest.raises(DatabaseIsolationError, match="is not a loopback address"):
        validate_test_database_isolation(
            test_url="postgresql+psycopg://user:pass@198.51.100.25:5432/app_test",
            primary_url="postgresql+psycopg://user:pass@localhost:5432/app",
            app_env="development",
        )


def test_empty_or_missing_test_url_fails():
    """Confirms missing test URL raises DatabaseIsolationError."""
    with pytest.raises(DatabaseIsolationError, match="Test database URL .* is not configured"):
        validate_test_database_isolation(
            test_url="",
            primary_url="postgresql+psycopg://user:pass@localhost:5432/app",
            app_env="development",
        )
