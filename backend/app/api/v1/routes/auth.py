from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Request, Response, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.security import (
    hash_password,
    verify_password,
    generate_session_token,
    hash_session_token,
    generate_csrf_token,
    login_rate_limiter,
    get_client_ip,
)
from backend.app.core.dependencies import (
    get_db,
    get_current_session,
    get_current_user,
    get_current_merchant,
    verify_csrf,
    set_session_cookie,
    clear_session_cookie,
)
from backend.app.models.user import User
from backend.app.models.merchant_profile import MerchantProfile
from backend.app.models.user_session import UserSession
from backend.app.repositories.user_repository import UserRepository
from backend.app.repositories.merchant_repository import MerchantRepository
from backend.app.repositories.session_repository import SessionRepository
from backend.app.schemas.auth import (
    RegisterRequest,
    LoginRequest,
    DeleteAccountRequest,
    AuthResponse,
    UserResponse,
    RefreshResponse,
)
from backend.app.schemas.merchant import MerchantResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user and merchant workspace",
)
def register(
    req: RegisterRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> AuthResponse:
    user_repo = UserRepository(db)
    merchant_repo = MerchantRepository(db)
    session_repo = SessionRepository(db)

    # Check for existing email (case-insensitive)
    existing_user = user_repo.get_by_email(req.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "EMAIL_ALREADY_EXISTS",
                    "message": "An account with this email address already exists",
                }
            },
        )

    # Hash password with Argon2id
    pw_hash = hash_password(req.password)

    # Create user
    user = user_repo.create(
        full_name=req.full_name,
        email=req.email,
        password_hash=pw_hash,
    )

    # Create associated 1:1 merchant profile
    merchant = merchant_repo.create(
        user_id=user.id,
        business_name=req.business_name,
        category=req.category,
        location=req.location,
    )

    # Issue session token
    raw_token = generate_session_token()
    token_hash = hash_session_token(raw_token)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.SESSION_TTL_MINUTES)
    session = session_repo.create(user.id, token_hash, expires_at)

    # Generate session-bound CSRF token
    csrf_token = generate_csrf_token(session.id, user.id)

    # Set secure HttpOnly session cookie
    set_session_cookie(response, raw_token)

    return AuthResponse(
        user=UserResponse.model_validate(user),
        merchant=MerchantResponse.model_validate(merchant),
        csrf_token=csrf_token,
    )


@router.post(
    "/login",
    response_model=AuthResponse,
    summary="Log in with email and password",
)
def login(
    req: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> AuthResponse:
    # Rate limit check per IP and normalized email
    client_ip = get_client_ip(request)
    normalized_email = req.email.lower().strip()
    rate_key = f"{client_ip}:{normalized_email}"

    if login_rate_limiter.is_rate_limited(rate_key, db=db):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": {
                    "code": "RATE_LIMIT_EXCEEDED",
                    "message": "Too many failed login attempts. Please try again later.",
                }
            },
        )

    user_repo = UserRepository(db)
    user = user_repo.get_by_email(normalized_email)

    # Constant-time verification check with generic error
    if not user or not verify_password(req.password, user.password_hash) or not user.is_active:
        login_rate_limiter.record_failure(
            rate_key,
            db=db,
            email=normalized_email,
            ip=client_ip,
            user_id=user.id if user else None,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "INVALID_CREDENTIALS",
                    "message": "Invalid email or password",
                }
            },
        )

    # Success: record success event in PostgreSQL
    login_rate_limiter.record_success(
        rate_key,
        db=db,
        email=normalized_email,
        ip=client_ip,
        user_id=user.id,
        merchant_id=None,
    )

    merchant_repo = MerchantRepository(db)
    merchant = merchant_repo.get_by_user_id(user.id)
    if not merchant:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": {
                    "code": "MERCHANT_PROFILE_MISSING",
                    "message": "Merchant profile not found for active user account",
                }
            },
        )

    # Create new session
    session_repo = SessionRepository(db)
    raw_token = generate_session_token()
    token_hash = hash_session_token(raw_token)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.SESSION_TTL_MINUTES)
    session = session_repo.create(user.id, token_hash, expires_at)

    csrf_token = generate_csrf_token(session.id, user.id)
    set_session_cookie(response, raw_token)

    return AuthResponse(
        user=UserResponse.model_validate(user),
        merchant=MerchantResponse.model_validate(merchant),
        csrf_token=csrf_token,
    )


@router.post(
    "/logout",
    summary="Log out and invalidate session",
)
def logout(
    response: Response,
    session: UserSession = Depends(get_current_session),
    _: None = Depends(verify_csrf),
    db: Session = Depends(get_db),
):
    session_repo = SessionRepository(db)
    session_repo.revoke(session.id)
    clear_session_cookie(response)
    return {"status": "ok"}


@router.get(
    "/me",
    response_model=AuthResponse,
    summary="Get current authenticated user and merchant workspace",
)
def get_me(
    user: User = Depends(get_current_user),
    merchant: MerchantProfile = Depends(get_current_merchant),
    session: UserSession = Depends(get_current_session),
) -> AuthResponse:
    csrf_token = generate_csrf_token(session.id, user.id)
    return AuthResponse(
        user=UserResponse.model_validate(user),
        merchant=MerchantResponse.model_validate(merchant),
        csrf_token=csrf_token,
    )


@router.post(
    "/refresh",
    response_model=RefreshResponse,
    summary="Rotate session token and refresh CSRF token",
)
def refresh_session(
    response: Response,
    session: UserSession = Depends(get_current_session),
    _: None = Depends(verify_csrf),
    db: Session = Depends(get_db),
) -> RefreshResponse:
    session_repo = SessionRepository(db)

    # Atomically rotate token
    new_raw_token = generate_session_token()
    new_token_hash = hash_session_token(new_raw_token)
    new_expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.SESSION_TTL_MINUTES)

    new_session = session_repo.rotate(session.id, new_token_hash, new_expires_at)
    if not new_session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "SESSION_ROTATION_FAILED", "message": "Failed to rotate session"}},
        )

    new_csrf_token = generate_csrf_token(new_session.id, session.user_id)
    set_session_cookie(response, new_raw_token)

    return RefreshResponse(csrf_token=new_csrf_token)


@router.delete(
    "/account",
    summary="Delete user account and all associated workspace data",
)
def delete_account(
    req: DeleteAccountRequest,
    response: Response,
    user: User = Depends(get_current_user),
    session: UserSession = Depends(get_current_session),
    _: None = Depends(verify_csrf),
    db: Session = Depends(get_db),
):
    # Require explicit password confirmation
    if not verify_password(req.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "INVALID_PASSWORD",
                    "message": "Incorrect password. Account deletion aborted.",
                }
            },
        )

    user_repo = UserRepository(db)
    session_repo = SessionRepository(db)

    # Invalidate sessions and delete user (cascades to merchant profile, etc.)
    session_repo.revoke_all_for_user(user.id)
    user_repo.delete(user.id)

    clear_session_cookie(response)
    return {"status": "ok", "message": "Account successfully deleted"}
