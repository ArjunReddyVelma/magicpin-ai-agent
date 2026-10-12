import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from backend.app.core.dependencies import (
    get_db,
    get_current_merchant,
    verify_csrf,
)
from backend.app.models.merchant_profile import MerchantProfile
from backend.app.repositories.action_repository import ActionRepository
from backend.app.schemas.action import (
    ActionResponse,
    ActionListResponse,
)

router = APIRouter(prefix="/actions", tags=["Suggested Actions & Human-in-the-Loop"])

ALLOWED_STATUSES = {"pending", "approved", "dismissed"}


@router.get(
    "",
    response_model=ActionListResponse,
    summary="List suggested actions for merchant review",
)
def list_actions(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status ('pending', 'approved', 'dismissed')"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    merchant: MerchantProfile = Depends(get_current_merchant),
    db: Session = Depends(get_db),
) -> ActionListResponse:
    if status_filter and status_filter not in ALLOWED_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "INVALID_STATUS",
                    "message": f"Status must be one of: {', '.join(sorted(ALLOWED_STATUSES))}",
                }
            },
        )

    repo = ActionRepository(db)
    items, total = repo.list_actions(
        merchant_id=merchant.id,
        status=status_filter,
        page=page,
        page_size=page_size,
    )
    return ActionListResponse(
        items=[ActionResponse.model_validate(a) for a in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{action_id}",
    response_model=ActionResponse,
    summary="Get single suggested action by ID",
)
def get_action(
    action_id: uuid.UUID,
    merchant: MerchantProfile = Depends(get_current_merchant),
    db: Session = Depends(get_db),
) -> ActionResponse:
    repo = ActionRepository(db)
    action = repo.get_by_id(merchant_id=merchant.id, action_id=action_id)
    if not action:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "ACTION_NOT_FOUND", "message": "Suggested action not found"}},
        )
    return ActionResponse.model_validate(action)


@router.post(
    "/{action_id}/approve",
    response_model=ActionResponse,
    summary="Record merchant approval decision for suggested action",
)
def approve_action(
    action_id: uuid.UUID,
    merchant: MerchantProfile = Depends(get_current_merchant),
    _: None = Depends(verify_csrf),
    db: Session = Depends(get_db),
) -> ActionResponse:
    repo = ActionRepository(db)
    action, ok = repo.transition_status(
        merchant_id=merchant.id,
        action_id=action_id,
        target_status="approved",
    )
    if action is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "ACTION_NOT_FOUND", "message": "Suggested action not found"}},
        )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "INVALID_ACTION_STATE",
                    "message": f"Action is already in '{action.status}' state and cannot be approved",
                }
            },
        )
    return ActionResponse.model_validate(action)


@router.post(
    "/{action_id}/dismiss",
    response_model=ActionResponse,
    summary="Record merchant dismissal decision for suggested action",
)
def dismiss_action(
    action_id: uuid.UUID,
    merchant: MerchantProfile = Depends(get_current_merchant),
    _: None = Depends(verify_csrf),
    db: Session = Depends(get_db),
) -> ActionResponse:
    repo = ActionRepository(db)
    action, ok = repo.transition_status(
        merchant_id=merchant.id,
        action_id=action_id,
        target_status="dismissed",
    )
    if action is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "ACTION_NOT_FOUND", "message": "Suggested action not found"}},
        )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "INVALID_ACTION_STATE",
                    "message": f"Action is already in '{action.status}' state and cannot be dismissed",
                }
            },
        )
    return ActionResponse.model_validate(action)
