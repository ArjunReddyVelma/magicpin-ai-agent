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
from backend.app.models import (
    User,
    MerchantProfile,
)

# Test Engine connecting strictly to magicpin_ai_agent_test
test_engine = create_engine(
    settings.DATABASE_URL_TEST,
    pool_pre_ping=True,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """
    Ensure test database schema is created via Alembic migrations.
    """
    alembic_cfg = Config("backend/alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL_TEST)
    alembic_cfg.set_main_option("script_location", "backend/migrations")

    # Run Alembic upgrade head to create all tables
    command.upgrade(alembic_cfg, "head")
    yield
    # Clean up test database after all tests
    command.downgrade(alembic_cfg, "base")


@pytest.fixture
def db_session() -> Session:
    """
    Provides a transactional database session rolled back after each test using savepoints.
    """
    connection = test_engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection, join_transaction_mode="create_savepoint")

    yield session

    session.close()
    if transaction.is_active:
        transaction.rollback()
    connection.close()


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
