from fastapi import APIRouter, HTTPException

from api.schemas import ContextRequest
from api.conversation_schemas import (
    CreateConversationRequest,
    CreateConversationResponse,
    AddMessageRequest,
)

from services.context_manager import ContextManager
from services.memory_manager import MemoryManager

router = APIRouter()

context_manager = ContextManager()
memory_manager = MemoryManager()


@router.post("/v1/context")
def save_context(request: ContextRequest):

    context_manager.update_context(
        request.merchant_id,
        request.context,
    )

    return {
        "status": "success",
        "merchant_id": request.merchant_id,
    }


@router.post(
    "/v1/conversations",
    response_model=CreateConversationResponse,
)
def create_conversation(request: CreateConversationRequest):

    conversation = memory_manager.create_conversation(
        merchant_id=request.merchant_id
    )

    return CreateConversationResponse(
        session_id=conversation.session_id,
        merchant_id=conversation.merchant_id,
    )


@router.get("/v1/conversations/{session_id}")
def get_conversation(session_id: str):

    conversation = memory_manager.get_conversation(session_id)

    if conversation is None:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found",
        )

    return conversation


@router.post("/v1/conversations/{session_id}/messages")
def add_message(
    session_id: str,
    request: AddMessageRequest,
):

    try:
        conversation = memory_manager.add_message(
            session_id=session_id,
            role=request.role,
            content=request.content,
        )

        return {
            "status": "success",
            "total_messages": len(conversation.messages),
        }

    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail=str(e),
        )