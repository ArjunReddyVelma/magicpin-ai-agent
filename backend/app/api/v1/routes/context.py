import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Request, Response, HTTPException, status, Query
from sqlalchemy.orm import Session

from backend.app.core.dependencies import (
    get_db,
    get_current_merchant,
    verify_csrf,
)
from backend.app.models.merchant_profile import MerchantProfile
from backend.app.repositories.context_repository import ContextRepository
from backend.app.schemas.context import (
    ContextItemResponse,
    ContextCreateRequest,
    ContextUpdateRequest,
    ContextListResponse,
    ContextItemType,
)

router = APIRouter(prefix="/context", tags=["Merchant Context"])


def _parse_etag(if_match_header: Optional[str]) -> Optional[int]:
    """Extracts integer version from an ETag/If-Match header like '\"1\"' or 'W/\"1\"' or '1'."""
    if not if_match_header:
        return None
    cleaned = if_match_header.strip()
    if cleaned.startswith("W/"):
        cleaned = cleaned[2:]
    cleaned = cleaned.strip('"\'')
    try:
        return int(cleaned)
    except ValueError:
        return None


@router.get(
    "",
    response_model=ContextListResponse,
    summary="List merchant context items",
)
def list_context_items(
    item_type: Optional[ContextItemType] = Query(None, description="Filter by context type"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    merchant: MerchantProfile = Depends(get_current_merchant),
    db: Session = Depends(get_db),
) -> ContextListResponse:
    repo = ContextRepository(db)
    items, total = repo.list_items(
        merchant_id=merchant.id,
        item_type=item_type,
        is_active=is_active,
        page=page,
        page_size=page_size,
    )
    return ContextListResponse(
        items=[ContextItemResponse.model_validate(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "",
    response_model=ContextItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new context item",
)
def create_context_item(
    req: ContextCreateRequest,
    response: Response,
    merchant: MerchantProfile = Depends(get_current_merchant),
    _: None = Depends(verify_csrf),
    db: Session = Depends(get_db),
) -> ContextItemResponse:
    repo = ContextRepository(db)
    item = repo.create(
        merchant_id=merchant.id,
        item_type=req.item_type,
        title=req.title,
        content=req.content,
        is_active=req.is_active,
    )
    response.headers["ETag"] = f'"{item.version}"'
    return ContextItemResponse.model_validate(item)


@router.get(
    "/{context_id}",
    response_model=ContextItemResponse,
    summary="Get single context item by ID",
)
def get_context_item(
    context_id: uuid.UUID,
    response: Response,
    merchant: MerchantProfile = Depends(get_current_merchant),
    db: Session = Depends(get_db),
) -> ContextItemResponse:
    repo = ContextRepository(db)
    item = repo.get_by_id(merchant_id=merchant.id, context_id=context_id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "CONTEXT_NOT_FOUND", "message": "Context item not found"}},
        )
    response.headers["ETag"] = f'"{item.version}"'
    return ContextItemResponse.model_validate(item)


@router.patch(
    "/{context_id}",
    response_model=ContextItemResponse,
    summary="Update context item with optimistic concurrency",
)
def update_context_item(
    context_id: uuid.UUID,
    req: ContextUpdateRequest,
    request: Request,
    response: Response,
    merchant: MerchantProfile = Depends(get_current_merchant),
    _: None = Depends(verify_csrf),
    db: Session = Depends(get_db),
) -> ContextItemResponse:
    # Determine expected version from If-Match header or body
    if_match = request.headers.get("If-Match")
    expected_version = _parse_etag(if_match)
    if expected_version is None:
        expected_version = req.expected_version

    if expected_version is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "VERSION_REQUIRED",
                    "message": "Optimistic concurrency requires If-Match header or expected_version in request body",
                }
            },
        )

    repo = ContextRepository(db)
    updated, is_conflict = repo.update_with_version(
        merchant_id=merchant.id,
        context_id=context_id,
        expected_version=expected_version,
        item_type=req.item_type,
        title=req.title,
        content=req.content,
        is_active=req.is_active,
    )

    if not updated and not is_conflict:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "CONTEXT_NOT_FOUND", "message": "Context item not found"}},
        )

    if is_conflict:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "STALE_VERSION_CONFLICT",
                    "message": "Stale version conflict: context item has been modified by another request.",
                    "details": {
                        "expected_version": expected_version,
                        "current_version": updated.version,
                    },
                }
            },
        )

    response.headers["ETag"] = f'"{updated.version}"'
    return ContextItemResponse.model_validate(updated)


@router.delete(
    "/{context_id}",
    summary="Delete context item by ID",
)
def delete_context_item(
    context_id: uuid.UUID,
    merchant: MerchantProfile = Depends(get_current_merchant),
    _: None = Depends(verify_csrf),
    db: Session = Depends(get_db),
):
    repo = ContextRepository(db)
    deleted = repo.delete(merchant_id=merchant.id, context_id=context_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "CONTEXT_NOT_FOUND", "message": "Context item not found"}},
        )
    return {"status": "ok", "message": "Context item successfully deleted"}
