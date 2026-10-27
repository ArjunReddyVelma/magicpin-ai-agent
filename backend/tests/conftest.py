import uuid
import pytest
from alembic.config import Config
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from backend.app.main import app
from backend.app.core.config import settings
from backend.app.core.dependencies import get_db
from backend.app.core.security import hash_password
from backend.app.core.db_safety import validate_test_database_isolation
from backend.app.db.session import check_database_connection
import backend.app.db.session as app_session_module
from backend.app.models import (
    User,
    MerchantProfile,
)

# Fail-closed database isolation check at test session startup
validate_test_database_isolation()

# Test Engine connecting strictly to verified test database
test_engine = create_engine(
    settings.DATABASE_URL_TEST,
    pool_pre_ping=True,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

# Divert global SessionLocal to bind to test_engine so that any un-overridden
# route dependency or direct call can NEVER connect to settings.DATABASE_URL.
app_session_module.SessionLocal = TestingSessionLocal


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """
    Ensure test database schema is created via Alembic migrations on verified test DB.
    Safe transaction rollbacks occur per-test via transactional savepoints in db_session.
    """
    validate_test_database_isolation()

    if not check_database_connection(test_engine):
        # Database unreachable (e.g. unit tests running without PostgreSQL active).
        # Yield without running migrations so unit tests can proceed safely.
        yield
        return

    alembic_cfg = Config("backend/alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL_TEST)
    alembic_cfg.set_main_option("script_location", "backend/migrations")

    # Run Alembic upgrade head to create all tables
    command.upgrade(alembic_cfg, "head")
    yield
    # Unsafe 'command.downgrade(alembic_cfg, "base")' removed to prevent accidental schema destruction.


@pytest.fixture
def db_session() -> Session:
    """
    Provides a transactional database session rolled back after each test using savepoints.
    """
    validate_test_database_isolation()

    if not check_database_connection(test_engine):
        pytest.skip("Test database (DATABASE_URL_TEST) is unavailable; skipping database test.")

    connection = test_engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection, join_transaction_mode="create_savepoint")

    yield session

    session.close()
    if transaction.is_active:
        transaction.rollback()
    connection.close()


@pytest.fixture(autouse=True)
def enforce_test_db_override(request):
    """
    Autouse fixture ensuring that any test requesting db_session
    automatically overrides FastAPI's get_db dependency for all TestClients.
    """
    if "db_session" in request.fixturenames:
        session = request.getfixturevalue("db_session")

        def override_get_db():
            yield session

        app.dependency_overrides[get_db] = override_get_db
        yield
        app.dependency_overrides.pop(get_db, None)
    else:
        yield


@pytest.fixture(autouse=True)
def isolate_whatsapp_mode_default(monkeypatch):
    """
    Ensures tests run with WHATSAPP_MODE='live' by default, isolating test
    execution from local .env values (e.g. WHATSAPP_MODE=mock).
    Tests specifically targeting mock mode explicitly set WHATSAPP_MODE='mock'.
    """
    monkeypatch.setattr(settings, "WHATSAPP_MODE", "live")


@pytest.fixture
def client(db_session: Session) -> TestClient:
    """
    FastAPI TestClient with get_db overridden to use the transactional test session.
    """
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def test_user(db_session: Session) -> User:
    user = User(
        full_name="Test Merchant Owner",
        email=f"owner_{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("ValidPassword123!"),
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def test_merchant(db_session: Session, test_user: User) -> MerchantProfile:
    merchant = MerchantProfile(
        user_id=test_user.id,
        business_name="Test Cafe & Bakery",
        category="Restaurant",
        location="Indiranagar, Bangalore",
        timezone="Asia/Kolkata",
    )
    db_session.add(merchant)
    db_session.flush()
    return merchant


@pytest.fixture
def second_merchant(db_session: Session) -> MerchantProfile:
    user = User(
        full_name="Second Merchant Owner",
        email=f"second_{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("ValidPassword123!"),
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    merchant = MerchantProfile(
        user_id=user.id,
        business_name="Other Retail Outlet",
        category="Retail",
        location="Koramangala, Bangalore",
        timezone="Asia/Kolkata",
    )
    db_session.add(merchant)
    db_session.flush()
    return merchant
