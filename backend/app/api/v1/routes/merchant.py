from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from backend.app.core.dependencies import (
    get_db,
    get_current_merchant,
    verify_csrf,
)
from backend.app.models.merchant_profile import MerchantProfile
from backend.app.repositories.merchant_repository import MerchantRepository
from backend.app.schemas.merchant import MerchantResponse, MerchantUpdateRequest

router = APIRouter(prefix="/merchant", tags=["Merchant Profile"])


@router.get(
    "",
    response_model=MerchantResponse,
    summary="Get current merchant workspace profile",
)
@router.get(
    "/profile",
    response_model=MerchantResponse,
    summary="Get current merchant workspace profile",
)
def get_merchant_profile(
    merchant: MerchantProfile = Depends(get_current_merchant),
) -> MerchantResponse:
    """
    Returns the merchant profile for the authenticated user session.
    Merchant ownership is derived strictly from session context.
    """
    return MerchantResponse.model_validate(merchant)


@router.patch(
    "",
    response_model=MerchantResponse,
    summary="Update merchant workspace profile",
)
@router.patch(
    "/profile",
    response_model=MerchantResponse,
    summary="Update merchant workspace profile",
)
def update_merchant_profile(
    req: MerchantUpdateRequest,
    merchant: MerchantProfile = Depends(get_current_merchant),
    _: None = Depends(verify_csrf),
    db: Session = Depends(get_db),
) -> MerchantResponse:
    """
    Updates the merchant profile fields for the authenticated user session.
    Protected by CSRF verification and strict merchant scoping.
    """
    merchant_repo = MerchantRepository(db)
    updated = merchant_repo.update(
        merchant_id=merchant.id,
        business_name=req.business_name,
        category=req.category,
        location=req.location,
        description=req.description,
        timezone=req.timezone,
    )
    return MerchantResponse.model_validate(updated)
