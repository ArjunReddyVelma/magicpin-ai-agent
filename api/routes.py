from fastapi import APIRouter, HTTPException

from api.schemas import ContextRequest
from api.conversation_schemas import (
    CreateConversationRequest,
    CreateConversationResponse,
    AddMessageRequest,
)
from api.chat_schemas import (
    ChatRequest,
    ChatResponse,
)

from services.context_manager import ContextManager
from services.memory_manager import MemoryManager
from services.prompt_builder import PromptBuilder
from services.llm_service import LLMService
from services.response_processor import ResponseProcessor
from services.chat_service import ChatService

router = APIRouter()

context_manager = ContextManager()
memory_manager = MemoryManager()
prompt_builder = PromptBuilder()
llm_service = LLMService()
response_processor = ResponseProcessor()


# -------------------------------------------------------------------
# Context APIs
# -------------------------------------------------------------------

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


# -------------------------------------------------------------------
# Conversation APIs
# -------------------------------------------------------------------

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


# -------------------------------------------------------------------
# Chat API
# -------------------------------------------------------------------

@router.post(
    "/v1/chat",
    response_model=ChatResponse,
)
def chat(request: ChatRequest):

    conversation = memory_manager.get_conversation(
        request.session_id
    )

    if conversation is None:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found",
        )

    if conversation.merchant_id != request.merchant_id:
        raise HTTPException(
            status_code=400,
            detail="Merchant ID does not match the conversation.",
        )

    # Save the latest user message
    memory_manager.add_message(
        session_id=request.session_id,
        role="user",
        content=request.message,
    )

    # Build prompt
    messages = prompt_builder.build_messages(
        merchant_id=request.merchant_id,
        session_id=request.session_id,
    )

    try:
        # Generate response from LLM
        response = llm_service.generate(messages)

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"LLM Error: {str(e)}",
        )

    # Process response
    response = response_processor.process(response)

    # Save assistant response
    memory_manager.add_message(
        session_id=request.session_id,
        role="assistant",
        content=response,
    )

    return ChatResponse(
        response=response
    )
chat_service = ChatService()
@router.post(
    "/v1/chat",
    response_model=ChatResponse,
)
def chat(request: ChatRequest):

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