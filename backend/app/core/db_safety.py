"""
Database isolation safety validation.

Provides fail-closed verification ensuring tests can never connect to, migrate,
or mutate the primary development database or any production/remote database.
"""
from typing import Optional
import ipaddress
import os
from sqlalchemy.engine import make_url

from backend.app.core.config import settings


class DatabaseIsolationError(RuntimeError):
    """Raised when database isolation safeguards detect an unsafe database target."""
    pass


# Known loopback/local host representations
LOCAL_HOSTS = {
    "localhost",
    "127.0.0.1",
    "::1",
    "0.0.0.0",
}

# Blocked database names that must NEVER be mutated or targeted by tests
BLOCKED_DB_NAMES = {
    "magicpin_ai_agent",
    "postgres",
    "template1",
    "master",
    "defaultdb",
}

# Remote cloud host suffixes indicating non-local environments
REMOTE_HOST_MARKERS = (
    ".render.com",
    ".amazonaws.com",
    ".rds.amazonaws.com",
    ".azure.com",
    ".supabase.co",
    ".elephantsql.com",
    ".neon.tech",
    ".cockroachlabs.cloud",
    ".fly.dev",
    ".herokuapp.com",
    ".heroku.com",
)


def validate_test_database_isolation(
    test_url: Optional[str] = None,
    primary_url: Optional[str] = None,
    app_env: Optional[str] = None,
) -> None:
    """
    Validates that test_url points to a confirmed, dedicated, disposable local test database.

    Enforces strict fail-closed criteria:
    1. Test URL must be configured and non-empty.
    2. Primary URL must be configured and non-empty.
    3. APP_ENV must not be 'production' or 'prod'.
    4. Test URL must differ from primary URL (both normalized and unmasked).
    5. Test database name must not equal primary database name.
    6. Test database name must not be in BLOCKED_DB_NAMES.
    7. Test database name must explicitly end with '_test'.
    8. Test database name must not contain production markers ('prod', 'live').
    9. Database name containing 'test' is NOT sufficient: host must also be verified
       as strictly local/loopback, and no remote cloud host markers may be present.
    10. If test host and port match primary host and port, database names MUST be disjoint.
    """
    effective_test_url = (
        getattr(settings, "DATABASE_URL_TEST", None)
        if test_url is None
        else test_url
    )
    effective_primary_url = (
        getattr(settings, "DATABASE_URL", None)
        if primary_url is None
        else primary_url
    )
    effective_env = (
        app_env
        or os.environ.get("APP_ENV")
        or getattr(settings, "APP_ENV", "development")
    ).strip().lower()

    # 1. Environment validation
    if effective_env in ("production", "prod"):
        raise DatabaseIsolationError(
            f"CRITICAL SAFETY VIOLATION: Tests cannot run in production environment (APP_ENV='{effective_env}')."
        )

    # 2. Presence checks
    if not effective_test_url or not str(effective_test_url).strip():
        raise DatabaseIsolationError(
            "CRITICAL SAFETY VIOLATION: Test database URL (DATABASE_URL_TEST) is not configured or empty."
        )

    if not effective_primary_url or not str(effective_primary_url).strip():
        raise DatabaseIsolationError(
            "CRITICAL SAFETY VIOLATION: Primary database URL (DATABASE_URL) is not configured or empty."
        )

    # 3. URL parsing
    try:
        test_parsed = make_url(str(effective_test_url).strip())
    except Exception as exc:
        raise DatabaseIsolationError(
            f"CRITICAL SAFETY VIOLATION: Malformed test database URL: {exc}"
        ) from exc

    try:
        primary_parsed = make_url(str(effective_primary_url).strip())
    except Exception as exc:
        raise DatabaseIsolationError(
            f"CRITICAL SAFETY VIOLATION: Malformed primary database URL: {exc}"
        ) from exc

    # 4. URL string disparity
    test_safe_str = test_parsed.render_as_string(hide_password=True).rstrip("/")
    primary_safe_str = primary_parsed.render_as_string(hide_password=True).rstrip("/")

    if test_safe_str == primary_safe_str:
        raise DatabaseIsolationError(
            f"CRITICAL SAFETY VIOLATION: Test database URL matches primary database URL ('{test_safe_str}'). "
            "Running tests would pollute or destroy the primary database."
        )

    # 5. Database name checks
    test_db = (test_parsed.database or "").strip().lower()
    primary_db = (primary_parsed.database or "").strip().lower()

    if not test_db:
        raise DatabaseIsolationError(
            "CRITICAL SAFETY VIOLATION: Test database URL has no database name specified."
        )

    if not primary_db:
        raise DatabaseIsolationError(
            "CRITICAL SAFETY VIOLATION: Primary database URL has no database name specified."
        )

    if test_db == primary_db:
        raise DatabaseIsolationError(
            f"CRITICAL SAFETY VIOLATION: Test database name '{test_db}' equals primary database name."
        )

    if test_db in BLOCKED_DB_NAMES:
        raise DatabaseIsolationError(
            f"CRITICAL SAFETY VIOLATION: Test database cannot target protected database '{test_db}'."
        )

    if any(marker in test_db for marker in ("prod", "live", "production")):
        raise DatabaseIsolationError(
            f"CRITICAL SAFETY VIOLATION: Test database name '{test_db}' contains forbidden production marker."
        )

    if not test_db.endswith("_test"):
        raise DatabaseIsolationError(
            f"CRITICAL SAFETY VIOLATION: Test database name '{test_db}' must end with '_test'."
        )

    # 6. Host inspection (verifying isolation beyond database name)
    test_host = (test_parsed.host or "").strip().lower()

    # If host is empty or None, it represents a local Unix domain socket
    if test_host:
        # Check against remote cloud markers
        for marker in REMOTE_HOST_MARKERS:
            if test_host.endswith(marker) or marker in test_host:
                raise DatabaseIsolationError(
                    f"CRITICAL SAFETY VIOLATION: Test database host '{test_host}' matches remote cloud host marker '{marker}'. "
                    "Tests must never target remote cloud infrastructure."
                )

        # Check against local host definitions
        if test_host not in LOCAL_HOSTS:
            try:
                addr = ipaddress.ip_address(test_host)
                if not addr.is_loopback:
                    raise DatabaseIsolationError(
                        f"CRITICAL SAFETY VIOLATION: Test database IP '{test_host}' is not a loopback address."
                    )
            except ValueError:
                # Not a valid IP address and not in LOCAL_HOSTS
                raise DatabaseIsolationError(
                    f"CRITICAL SAFETY VIOLATION: Test database host '{test_host}' is not a recognized local loopback host."
                )

    # 7. Disjoint database confirmation when on the same host/port
    primary_host = (primary_parsed.host or "").strip().lower()
    if (test_host == primary_host) and (test_parsed.port == primary_parsed.port):
        if test_db == primary_db:
            raise DatabaseIsolationError(
                f"CRITICAL SAFETY VIOLATION: Test target exactly matches primary instance and database '{test_db}'."
            )
