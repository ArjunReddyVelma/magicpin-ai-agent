import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from backend.app.ai.provider import LLMProvider
from backend.app.core.dependencies import get_db, get_llm_provider
from backend.app.core.security import get_client_ip
from backend.app.core.support_rate_limiter import support_rate_limiter
from backend.app.schemas.customer_support import (
    PublicMerchantProfileResponse,
    CreateCustomerSessionRequest,
    CreateCustomerSessionResponse,
    CustomerInquiryRequest,
    CustomerInquiryResponse,
    CustomerHistoryResponse,
)
from backend.app.services.customer_support_service import CustomerSupportService

router = APIRouter(prefix="/public/support", tags=["Public Customer Support"])


@router.get(
    "/merchants/{merchant_id}",
    response_model=PublicMerchantProfileResponse,
    status_code=status.HTTP_200_OK,
    summary="Get allowlisted public merchant profile for customer support",
)
def get_public_merchant_profile(
    merchant_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> PublicMerchantProfileResponse:
    service = CustomerSupportService(db=db)
    return service.get_public_merchant_profile(merchant_id)


@router.post(
    "/sessions",
    response_model=CreateCustomerSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new customer support session",
)
def create_customer_session(
    req: CreateCustomerSessionRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> CreateCustomerSessionResponse:
    # -------------------------------------------------------------------------
    # Transaction Boundary Rationale (Session Creation):
    # 1. support_rate_limiter.check_session_creation: Fast-path non-locking check.
    # 2. support_rate_limiter.record_session_creation: Acquires transaction-scoped
    #    PostgreSQL advisory lock, re-evaluates quota, inserts AuditEvent, and commits.
    #    Advisory locks are transaction-scoped and released when the rate-limit
    #    transaction commits or rolls back. Completing this transaction before downstream
    #    merchant lookup and token hashing minimizes lock holding time; actual lock
    #    duration depends on database execution and contention.
    # 3. service.create_customer_session: Executes business transaction (merchant
    #    validation, session token generation, cryptographic hashing, and persistence).
    # -------------------------------------------------------------------------
    client_ip = get_client_ip(request)
    support_rate_limiter.check_session_creation(client_ip, db=db)
    support_rate_limiter.record_session_creation(client_ip, db=db)

    service = CustomerSupportService(db=db)
    session, raw_token = service.create_customer_session(
        merchant_id=req.merchant_id,
        customer_name=req.customer_name,
    )

    return CreateCustomerSessionResponse(
        session_id=session.id,
        customer_token=raw_token,
        status=session.status,
        created_at=session.created_at,
    )


@router.post(
    "/sessions/{session_id}/messages",
    response_model=CustomerInquiryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a customer support inquiry",
)
def submit_customer_inquiry(
    session_id: uuid.UUID,
    req: CustomerInquiryRequest,
    request: Request,
    x_customer_token: Optional[str] = Header(None, alias="X-Customer-Token"),
    db: Session = Depends(get_db),
    llm_provider: LLMProvider = Depends(get_llm_provider),
) -> CustomerInquiryResponse:
    # -------------------------------------------------------------------------
    # Transaction Boundary Rationale (Message Submission):
    # 1. support_rate_limiter.check_message_submission: Fast-path non-locking quota
    #    pre-check to quickly reject saturated IPs/sessions with HTTP 429.
    # 2. service.verify_customer_session: Authenticates customer token and verifies
    #    active session status. Must run BEFORE consuming quota to prevent invalid
    #    or unauthenticated requests from exhausting legitimate session quotas.
    # 3. support_rate_limiter.record_message_submission: Acquires bounded transaction-scoped
    #    PostgreSQL advisory locks (sorted ascending to prevent deadlocks), verifies
    #    authoritative counts inside lock, batch-inserts AuditEvents, and COMMITS immediately.
    #    - Concurrency Rationale: Advisory locks are transaction-scoped and released
    #      when the rate-limit transaction commits or rolls back. Completing this
    #      transaction before downstream inquiry persistence and LLM generation ensures
    #      locks are not held across external API calls, preventing lock wait timeouts
    #      (3.0s) and thread starvation; actual lock duration depends on database
    #      execution and contention.
    #    - Security Rationale: Quota consumption is durable prior to business processing.
    #      A downstream failure or malformed payload cannot be exploited to retry
    #      indefinitely without consuming quota.
    #    - Session Expiration Safety: The commit expires SQLAlchemy's identity map.
    #      Subsequent access to session attributes safely re-queries via the open db
    #      connection, and service.submit_customer_inquiry issues an explicit db.refresh(msg)
    #      guaranteeing all response attributes are loaded without lazy-loading errors.
    # 4. service.submit_customer_inquiry: Persists the inquiry first (commit=True),
    #    then executes grounded AI draft generation and commits the draft/error state.
    # -------------------------------------------------------------------------
    client_ip = get_client_ip(request)
    support_rate_limiter.check_message_submission(client_ip, session_id, db=db)

    service = CustomerSupportService(db=db, llm_provider=llm_provider)
    session = service.verify_customer_session(session_id, x_customer_token)

    support_rate_limiter.record_message_submission(client_ip, session_id, db=db)

    msg = service.submit_customer_inquiry(
        session_id=session.id,
        customer_token=x_customer_token,
        content=req.content,
        session=session,
    )

    return CustomerInquiryResponse(
        id=msg.id,
        session_id=msg.session_id,
        customer_text=msg.customer_text,
        status=msg.status,
        created_at=msg.created_at,
    )


@router.get(
    "/sessions/{session_id}/messages",
    response_model=CustomerHistoryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get customer support message history for a session",
)
def get_customer_history(
    session_id: uuid.UUID,
    x_customer_token: Optional[str] = Header(None, alias="X-Customer-Token"),
    limit: int = Query(100, ge=1, le=100),
    db: Session = Depends(get_db),
) -> CustomerHistoryResponse:
    service = CustomerSupportService(db=db)
    return service.get_customer_history(
        session_id=session_id,
        customer_token=x_customer_token,
        limit=limit,
    )
