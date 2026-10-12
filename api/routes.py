from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from api.schemas import (
    ContextPushRequest,
    ContextPushResponse,
)

from api.conversation_schemas import (
    CreateConversationRequest,
    CreateConversationResponse,
    AddMessageRequest,
)

from api.chat_schemas import (
    ChatRequest,
    ChatResponse,
)

from api.tick_schemas import (
    TickRequest,
    TickResponse,
)
from api.reply_schemas import (
    ReplyRequest,
    ReplyResponse,
)

from services.reply_service import ReplyService
from services.context_manager import ContextManager
from services.memory_manager import MemoryManager
from services.chat_service import ChatService
from services.engagement_planner import EngagementPlanner


router = APIRouter()


# -------------------------------------------------------------------
# Service Instances
# -------------------------------------------------------------------

context_manager = ContextManager()
memory_manager = MemoryManager()
chat_service = ChatService()
engagement_planner = EngagementPlanner()
reply_service = ReplyService()

# -------------------------------------------------------------------
# Context API
# -------------------------------------------------------------------

@router.post(
    "/v1/context",
    response_model=ContextPushResponse,
)
def save_context(request: ContextPushRequest):

    try:
        result, current_version = context_manager.save_context(
            scope=request.scope,
            context_id=request.context_id,
            version=request.version,
            payload=request.payload,
            delivered_at=request.delivered_at,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={
                "accepted": False,
                "reason": "invalid_scope",
                "details": str(e),
            },
        )

    # Older version
    if result == "stale":
        return JSONResponse(
            status_code=409,
            content={
                "accepted": False,
                "reason": "stale_version",
                "current_version": current_version,
            },
        )

    # Created / Updated / Duplicate
    return ContextPushResponse(
        accepted=True,
        ack_id=context_manager.generate_ack_id(),
        stored_at=context_manager.current_timestamp(),
    )


# -------------------------------------------------------------------
# Conversation APIs
# -------------------------------------------------------------------

@router.post(
    "/v1/conversations",
    response_model=CreateConversationResponse,
)
def create_conversation(
    request: CreateConversationRequest,
):

    conversation = memory_manager.create_conversation(
        merchant_id=request.merchant_id
    )

    return CreateConversationResponse(
        session_id=conversation.session_id,
        merchant_id=conversation.merchant_id,
    )


@router.get(
    "/v1/conversations/{session_id}"
)
def get_conversation(
    session_id: str,
):

    conversation = memory_manager.get_conversation(
        session_id
    )

    if conversation is None:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found",
        )

    return conversation


@router.post(
    "/v1/conversations/{session_id}/messages"
)
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
            "total_messages": len(
                conversation.messages
            ),
        }

    except ValueError as e:

        raise HTTPException(
            status_code=404,
            detail=str(e),
        )


# -------------------------------------------------------------------
# Chat API
# -------------------------------------------------------------------

@router.post(
    "/v1/chat",
    response_model=ChatResponse,
)
def chat(
    request: ChatRequest,
):

    try:

        response = chat_service.chat(
            merchant_id=request.merchant_id,
            session_id=request.session_id,
            message=request.message,
        )

        return ChatResponse(
            response=response
        )

    except ValueError as e:

        raise HTTPException(
            status_code=400,
            detail=str(e),
        )

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=f"LLM Error: {str(e)}",
        )


# -------------------------------------------------------------------
# Tick API
# -------------------------------------------------------------------

@router.post(
    "/v1/tick",
    response_model=TickResponse,
)
def tick(
    request: TickRequest,
):

    try:

        actions = engagement_planner.plan(
            now=request.now,
            available_triggers=request.available_triggers,
        )

        return TickResponse(
            actions=actions
        )

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=f"Tick error: {str(e)}",
        )

# -------------------------------------------------------------------
# Reply API
# -------------------------------------------------------------------

@router.post(
    "/v1/reply",
    response_model=ReplyResponse,
)
def reply(request: ReplyRequest):

    try:

        result = reply_service.reply(
            conversation_id=request.conversation_id,
            merchant_id=request.merchant_id,
            message=request.message,
            turn_number=request.turn_number,
        )

        return ReplyResponse(
            **result
        )

    except ValueError as e:

        raise HTTPException(
            status_code=400,
            detail=str(e),
        )

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=f"Reply error: {str(e)}",
        )