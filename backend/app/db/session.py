from typing import Generator
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from backend.app.core.config import settings

# Engine with connection pool
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """
    Dependency that provides a database session per request.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_database_connection(custom_engine=None) -> bool:
    """
    Executes SELECT 1 against PostgreSQL to verify connectivity.
    """
    target_engine = custom_engine or engine
    try:
        with target_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
