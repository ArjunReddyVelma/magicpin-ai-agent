import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, Header
from sqlalchemy.orm import Session

from backend.app.core.dependencies import (
    get_db,
    get_current_merchant,
    verify_csrf,
    get_llm_provider,
)
from backend.app.ai.provider import LLMProvider
from backend.app.services.chat_service import ChatService
from backend.app.models.merchant_profile import MerchantProfile
from backend.app.repositories.conversation_repository import ConversationRepository
from backend.app.repositories.message_repository import MessageRepository
from backend.app.schemas.conversation import (
    ConversationResponse,
    ConversationCreateRequest,
    ConversationUpdateRequest,
    ConversationListResponse,
)
from backend.app.schemas.message import (
    MessageResponse,
    MessageListResponse,
    MessageCreateRequest,
    ChatResponse,
)

router = APIRouter(prefix="/conversations", tags=["Conversations & History"])


@router.get(
    "",
    response_model=ConversationListResponse,
    summary="List merchant conversations",
)
def list_conversations(
    status: Optional[str] = Query(None, description="Filter by status ('active', 'archived')"),
    query: Optional[str] = Query(None, description="Search by conversation title"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    merchant: MerchantProfile = Depends(get_current_merchant),
    db: Session = Depends(get_db),
) -> ConversationListResponse:
    repo = ConversationRepository(db)
    items, total = repo.list_conversations(
        merchant_id=merchant.id,
        status=status,
        query=query,
        page=page,
        page_size=page_size,
    )
    return ConversationListResponse(
        items=[ConversationResponse.model_validate(c) for c in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new conversation",
)
def create_conversation(
    req: ConversationCreateRequest,
    merchant: MerchantProfile = Depends(get_current_merchant),
    _: None = Depends(verify_csrf),
    db: Session = Depends(get_db),
) -> ConversationResponse:
    repo = ConversationRepository(db)
    conv = repo.create(merchant_id=merchant.id, title=req.title)
    return ConversationResponse.model_validate(conv)


@router.get(
    "/{conversation_id}",
    response_model=ConversationResponse,
    summary="Get conversation details by ID",
)
def get_conversation(
    conversation_id: uuid.UUID,
    merchant: MerchantProfile = Depends(get_current_merchant),
    db: Session = Depends(get_db),
) -> ConversationResponse:
    repo = ConversationRepository(db)
    conv = repo.get_by_id(merchant_id=merchant.id, conversation_id=conversation_id)
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "CONVERSATION_NOT_FOUND", "message": "Conversation not found"}},
        )
    return ConversationResponse.model_validate(conv)


@router.patch(
    "/{conversation_id}",
    response_model=ConversationResponse,
    summary="Update conversation title or status",
)
def update_conversation(
    conversation_id: uuid.UUID,
    req: ConversationUpdateRequest,
    merchant: MerchantProfile = Depends(get_current_merchant),
    _: None = Depends(verify_csrf),
    db: Session = Depends(get_db),
) -> ConversationResponse:
    repo = ConversationRepository(db)
    conv = repo.update(
        merchant_id=merchant.id,
        conversation_id=conversation_id,
        title=req.title,
        status=req.status,
    )
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "CONVERSATION_NOT_FOUND", "message": "Conversation not found"}},
        )
    return ConversationResponse.model_validate(conv)


@router.delete(
    "/{conversation_id}",
    summary="Delete conversation and associated messages",
)
def delete_conversation(
    conversation_id: uuid.UUID,
    merchant: MerchantProfile = Depends(get_current_merchant),
    _: None = Depends(verify_csrf),
    db: Session = Depends(get_db),
):
    repo = ConversationRepository(db)
    deleted = repo.delete(merchant_id=merchant.id, conversation_id=conversation_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "CONVERSATION_NOT_FOUND", "message": "Conversation not found"}},
        )
    return {"status": "ok", "message": "Conversation successfully deleted"}


@router.get(
    "/{conversation_id}/messages",
    response_model=MessageListResponse,
    summary="Get paginated messages for a conversation",
)
def list_conversation_messages(
    conversation_id: uuid.UUID,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    before: Optional[datetime] = Query(None, description="Filter messages before timestamp"),
    merchant: MerchantProfile = Depends(get_current_merchant),
    db: Session = Depends(get_db),
) -> MessageListResponse:
    # First verify conversation belongs to authenticated merchant
    conv_repo = ConversationRepository(db)
    conv = conv_repo.get_by_id(merchant_id=merchant.id, conversation_id=conversation_id)
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "CONVERSATION_NOT_FOUND", "message": "Conversation not found"}},
        )

    msg_repo = MessageRepository(db)
    messages, total = msg_repo.list_messages(
        conversation_id=conversation_id,
        page=page,
        page_size=page_size,
        before=before,
    )
    return MessageListResponse(
        items=[MessageResponse.model_validate(m) for m in messages],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/{conversation_id}/messages",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Send a message and receive a grounded AI assistant response",
)
def send_chat_message(
    conversation_id: uuid.UUID,
    req: MessageCreateRequest,
    merchant: MerchantProfile = Depends(get_current_merchant),
    provider: LLMProvider = Depends(get_llm_provider),
    idempotency_header: Optional[str] = Header(None, alias="Idempotency-Key"),
    _: None = Depends(verify_csrf),
    db: Session = Depends(get_db),
) -> ChatResponse:
    chat_service = ChatService()
    idempotency_key = req.idempotency_key or idempotency_header
    return chat_service.send_message(
        merchant=merchant,
        conversation_id=conversation_id,
        content=req.content,
        db=db,
        provider=provider,
        idempotency_key=idempotency_key,
        retry_message_id=req.retry_message_id,
    )

