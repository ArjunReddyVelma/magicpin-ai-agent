import uuid
from datetime import datetime, timezone
from typing import Generator, Optional
from fastapi import Request, Response, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.security import hash_session_token, verify_csrf_token
from backend.app.db.session import SessionLocal
from backend.app.models.user import User
from backend.app.models.merchant_profile import MerchantProfile
from backend.app.models.user_session import UserSession
from backend.app.repositories.user_repository import UserRepository
from backend.app.repositories.merchant_repository import MerchantRepository
from backend.app.repositories.session_repository import SessionRepository


def get_db() -> Generator[Session, None, None]:
    """Provides a database session from the connection pool."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def set_session_cookie(response: Response, token: str) -> None:
    """Sets the secure, HttpOnly session cookie on the response."""
    response.set_cookie(
        key=settings.COOKIE_NAME,
        value=token,
        max_age=settings.SESSION_TTL_MINUTES * 60,
        httponly=True,
        samesite=settings.COOKIE_SAMESITE,
        secure=settings.COOKIE_SECURE or (settings.APP_ENV == "production"),
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    """Clears the session cookie from the client."""
    response.delete_cookie(
        key=settings.COOKIE_NAME,
        path="/",
        httponly=True,
        samesite=settings.COOKIE_SAMESITE,
        secure=settings.COOKIE_SECURE or (settings.APP_ENV == "production"),
    )


def get_current_session(
    request: Request,
    db: Session = Depends(get_db),
) -> UserSession:
    """
    Validates the session cookie against user_sessions table.
    Ensures session exists, is not revoked, and is not expired.
    Touches last_seen_at upon valid request.
    """
    token = request.cookies.get(settings.COOKIE_NAME)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "UNAUTHORIZED", "message": "Authentication required"}},
        )

    token_hash = hash_session_token(token)
    session_repo = SessionRepository(db)
    session = session_repo.get_by_token_hash(token_hash)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "UNAUTHORIZED", "message": "Invalid or expired session"}},
        )

    if session.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "UNAUTHORIZED", "message": "Session has been revoked"}},
        )

    now = datetime.now(timezone.utc)
    # Ensure timezone comparison works
    session_expires = session.expires_at
    if session_expires.tzinfo is None:
        session_expires = session_expires.replace(tzinfo=timezone.utc)

    if session_expires <= now:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "UNAUTHORIZED", "message": "Session has expired"}},
        )

    session_repo.touch(session.id)
    return session


def get_current_user(
    session: UserSession = Depends(get_current_session),
    db: Session = Depends(get_db),
) -> User:
    """
    Resolves active user from the validated session.
    """
    user_repo = UserRepository(db)
    user = user_repo.get_by_id(session.user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "UNAUTHORIZED", "message": "User account inactive or not found"}},
        )
    return user


def get_current_merchant(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MerchantProfile:
    """
    Derives merchant ownership EXCLUSIVELY from the authenticated user session.
    Never accepts or trusts client-supplied merchant_id for authorization.
    """
    merchant_repo = MerchantRepository(db)
    merchant = merchant_repo.get_by_user_id(user.id)
    if not merchant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "MERCHANT_NOT_FOUND", "message": "Merchant profile not found for user"}},
        )
    return merchant


def verify_csrf(
    request: Request,
    session: UserSession = Depends(get_current_session),
) -> None:
    """
    Enforces session-bound CSRF token validation on unsafe state-changing requests.
    Validates X-CSRF-Token header against expected HMAC of session UUID and user UUID.
    """
    submitted_token = request.headers.get("X-CSRF-Token")
    if not submitted_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "CSRF_TOKEN_MISSING", "message": "Missing CSRF token header"}},
        )

    if not verify_csrf_token(submitted_token, session.id, session.user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "CSRF_TOKEN_INVALID", "message": "Invalid CSRF token"}},
        )
