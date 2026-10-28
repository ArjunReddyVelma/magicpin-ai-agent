import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from backend.app.core.dependencies import (
    get_db,
    get_current_merchant,
    verify_csrf,
)
from backend.app.models.merchant_profile import MerchantProfile
from backend.app.schemas.customer_support import (
    MerchantSupportListResponse,
    MerchantSupportMessageResponse,
    MerchantEditReplyRequest,
    DeliverReplyRequest,
)
from backend.app.services.customer_support_service import CustomerSupportService

router = APIRouter(prefix="/support", tags=["Merchant Web Support"])


@router.get(
    "/messages",
    response_model=MerchantSupportListResponse,
    status_code=status.HTTP_200_OK,
    summary="List customer support inquiries for authenticated merchant",
)
def list_messages(
    status: Optional[str] = Query(
        None,
        description="Filter by message status (e.g. needs_review, delivered, dismissed)",
    ),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    merchant: MerchantProfile = Depends(get_current_merchant),
    db: Session = Depends(get_db),
) -> MerchantSupportListResponse:
    service = CustomerSupportService(db=db)
    return service.list_merchant_messages(
        merchant_id=merchant.id,
        status=status,
        page=page,
        page_size=page_size,
    )


@router.patch(
    "/messages/{message_id}",
    response_model=MerchantSupportMessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Edit AI suggested reply for a pending customer support inquiry",
)
def edit_suggested_reply(
    message_id: uuid.UUID,
    req: MerchantEditReplyRequest,
    merchant: MerchantProfile = Depends(get_current_merchant),
    _: None = Depends(verify_csrf),
    db: Session = Depends(get_db),
) -> MerchantSupportMessageResponse:
    service = CustomerSupportService(db=db)
    return service.edit_merchant_suggested_reply(
        message_id=message_id,
        merchant_id=merchant.id,
        suggested_reply=req.suggested_reply,
    )


@router.post(
    "/messages/{message_id}/deliver",
    response_model=MerchantSupportMessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Approve and deliver reply to a customer support inquiry",
)
def deliver_reply(
    message_id: uuid.UUID,
    req: DeliverReplyRequest = DeliverReplyRequest(),
    merchant: MerchantProfile = Depends(get_current_merchant),
    _: None = Depends(verify_csrf),
    db: Session = Depends(get_db),
) -> MerchantSupportMessageResponse:
    service = CustomerSupportService(db=db)
    return service.deliver_merchant_reply(
        message_id=message_id,
        merchant_id=merchant.id,
        reply_text=req.reply_text,
    )


@router.post(
    "/messages/{message_id}/dismiss",
    response_model=MerchantSupportMessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Dismiss a customer support inquiry",
)
def dismiss_message(
    message_id: uuid.UUID,
    merchant: MerchantProfile = Depends(get_current_merchant),
    _: None = Depends(verify_csrf),
    db: Session = Depends(get_db),
) -> MerchantSupportMessageResponse:
    service = CustomerSupportService(db=db)
    return service.dismiss_merchant_message(
        message_id=message_id,
        merchant_id=merchant.id,
    )
