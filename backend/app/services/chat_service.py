import uuid
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.ai.provider import LLMProvider
from backend.app.ai.prompt_builder import PromptBuilder
from backend.app.ai.context_retriever import ContextRetriever
from backend.app.ai.response_validator import ResponseValidator
from backend.app.core.logging import logger
from backend.app.models.merchant_profile import MerchantProfile
from backend.app.models.conversation import Conversation
from backend.app.models.message import Message
from backend.app.models.suggested_action import SuggestedAction

from backend.app.repositories.conversation_repository import ConversationRepository
from backend.app.repositories.message_repository import MessageRepository
from backend.app.repositories.action_repository import ActionRepository
from backend.app.schemas.message import (
    MessageResponse,
    ContextUsedItem,
    ChatResponse,
)


class ChatService:
    """
    Coordinates end-to-end AI chat interaction:
    - Authorizes conversation ownership for merchant
    - Handles message idempotency and failed-message retry paths
    - Persists user message before model invocation
    - Gathers bounded history and relevant active merchant context
    - Calls LLMProvider with timeouts and error handling
    - On failure: updates user message to 'failed' and returns 502 with retry details
    - On success: validates output, persists assistant message, updates conversation last_message_at
    """

    def __init__(
        self,
        context_retriever: Optional[ContextRetriever] = None,
        prompt_builder: Optional[PromptBuilder] = None,
        response_validator: Optional[ResponseValidator] = None,
    ):
        self.context_retriever = context_retriever or ContextRetriever()
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.response_validator = response_validator or ResponseValidator()

    @staticmethod
    def _is_draft_eligible(user_content: str, assistant_content: str) -> bool:
        """
        Narrow deterministic eligibility rule for customer-support draft actions.
        Requires both drafting intent (draft/reply/respond) and customer/order context.
        """
        if not user_content or not assistant_content:
            return False

        user_lower = user_content.lower().strip()
        assistant_lower = assistant_content.lower().strip()

        # Guard against short greetings, empty inputs, or error fallbacks
        if len(user_lower) < 5 or len(assistant_lower) < 20:
            return False
        if assistant_lower.startswith("i apologize, but i could not generate a response"):
            return False

        # Direct drafting and reply intent verbs / phrases
        draft_verbs = (
            "draft",
            "reply",
            "respond",
            "response",
            "apologize",
            "apology",
            "how to reply",
            "how to respond",
            "how should i reply",
            "how should i respond",
            "what should i reply",
            "what should i say",
            "what should i tell",
        )
        has_draft_intent = any(verb in user_lower for verb in draft_verbs)

        # Customer, order, and support context keywords
        customer_indicators = (
            "customer",
            "client",
            "order",
            "delivery",
            "refund",
            "complaint",
            "delayed",
            "delay",
            "cancel",
            "cancellation",
            "buyer",
            "guest",
        )
        has_customer_context = any(ind in user_lower for ind in customer_indicators)

        return has_draft_intent and has_customer_context

    @staticmethod
    def _generate_action_title(conversation_title: Optional[str], user_content: str) -> str:
        if conversation_title and conversation_title.strip() and conversation_title.strip().lower() != "new conversation":
            return f"Customer Reply: {conversation_title.strip()}"[:200]
        snippet = " ".join(user_content.strip().split())[:60]
        return f"Reply Draft: {snippet}"[:200]

    def send_message(
        self,
        merchant: MerchantProfile,
        conversation_id: uuid.UUID,
        content: str,
        db: Session,
        provider: LLMProvider,
        idempotency_key: Optional[str] = None,
        retry_message_id: Optional[uuid.UUID] = None,
    ) -> ChatResponse:
        user_msg: Optional[Message] = None
        try:
            # 1. Authorize conversation and acquire row-level lock to serialize concurrent turns
            stmt = (
                select(Conversation)
                .where(
                    Conversation.id == conversation_id,
                    Conversation.merchant_id == merchant.id,
                )
                .with_for_update()
            )
            conv = db.scalars(stmt).first()
            if not conv:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"error": {"code": "CONVERSATION_NOT_FOUND", "message": "Conversation not found"}},
                )
            if conv.status == "archived":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"error": {"code": "CONVERSATION_ARCHIVED", "message": "Cannot send messages to an archived conversation"}},
                )

            msg_repo = MessageRepository(db)

            # 2. Check retry path with strict ownership, conversation, and failure status validation
            if retry_message_id:
                candidate = msg_repo.get_by_id(conversation_id=conversation_id, message_id=retry_message_id)
                if not candidate:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail={"error": {"code": "RETRY_MESSAGE_NOT_FOUND", "message": "Failed message to retry was not found in this conversation"}},
                    )
                if candidate.role != "user":
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail={"error": {"code": "INVALID_RETRY_TARGET", "message": "Only user messages can be retried"}},
                    )
                if candidate.status == "complete":
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail={"error": {"code": "MESSAGE_ALREADY_COMPLETED", "message": "Message turn has already completed successfully"}},
                    )
                user_msg = candidate
                if content and content.strip():
                    user_msg.content = content.strip()
                # Note: user_msg.status remains 'failed' during retry attempt;
                # it is only transitioned to 'complete' once assistant response succeeds.
                db.flush()

            # 3. Check idempotency key if user_msg is not already resolved
            if not user_msg and idempotency_key:
                # Prevent reusing idempotency key across different conversations
                cross_stmt = select(Message).where(
                    Message.conversation_id != conversation_id,
                    Message.role == "user",
                    Message.context_metadata.op("->>")("idempotency_key") == idempotency_key,
                )
                if db.scalars(cross_stmt).first():
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail={
                            "error": {
                                "code": "IDEMPOTENCY_KEY_REUSED",
                                "message": "Idempotency key has already been used in another conversation",
                            }
                        },
                    )

                # Query existing message with this idempotency key in current conversation
                stmt = select(Message).where(
                    Message.conversation_id == conversation_id,
                    Message.role == "user",
                    Message.context_metadata.op("->>")("idempotency_key") == idempotency_key,
                )
                existing_user_msg = db.scalars(stmt).first()
                if existing_user_msg:
                    if existing_user_msg.status == "failed":
                        user_msg = existing_user_msg
                        if content and content.strip():
                            user_msg.content = content.strip()
                        # Remains 'failed' until generation succeeds
                        db.flush()
                    else:
                        # Look for existing assistant response
                        astmt = (
                            select(Message)
                            .where(
                                Message.conversation_id == conversation_id,
                                Message.role == "assistant",
                                Message.created_at >= existing_user_msg.created_at,
                            )
                            .order_by(Message.created_at.asc())
                        )
                        existing_assistant = db.scalars(astmt).first()
                        if existing_assistant:
                            # Release row lock and return cached completed turn
                            if db.in_transaction():
                                db.rollback()
                            sources = (existing_assistant.context_metadata or {}).get("sources", [])
                            context_used = []
                            for s in sources:
                                try:
                                    context_used.append(
                                        ContextUsedItem(
                                            context_id=uuid.UUID(s["context_id"]),
                                            title=s["title"],
                                            item_type=s["item_type"],
                                            version=s.get("version", 1),
                                        )
                                    )
                                except Exception:
                                    pass
                            return ChatResponse(
                                user_message=MessageResponse.model_validate(existing_user_msg),
                                assistant_message=MessageResponse.model_validate(existing_assistant),
                                context_used=context_used,
                            )
                        user_msg = existing_user_msg

            # 4. If no existing message, persist new user message initially as 'failed'
            # to ensure it is never marked complete before its required operation has succeeded.
            # Flushed (not committed) to keep Conversation row lock held across provider call.
            if not user_msg:
                metadata = {"idempotency_key": idempotency_key} if idempotency_key else None
                user_msg = msg_repo.create(
                    conversation_id=conversation_id,
                    role="user",
                    content=content.strip(),
                    status="failed",
                    context_metadata=metadata,
                    commit=False,
                )

            # 5. Retrieve active context and history
            context_items = self.context_retriever.retrieve_relevant_context(
                merchant_id=merchant.id,
                query=user_msg.content,
                db=db,
            )
            raw_history = msg_repo.get_recent_history(conversation_id=conversation_id, limit=10)
            history = [m for m in raw_history if m.id != user_msg.id]

            system_prompt = self.prompt_builder.build_system_prompt(merchant, context_items)
            messages_payload = self.prompt_builder.build_messages_payload(history, user_msg.content)

            # 6. Call LLM provider
            try:
                response = provider.generate_response(
                    system_prompt=system_prompt,
                    messages=messages_payload,
                )
            except Exception as exc:
                # User message remains marked failed in DB; commit releases row lock on provider failure / timeout
                user_msg.status = "failed"
                failed_id_str = str(user_msg.id)
                db.commit()
                logger.error("LLM generation failed for conversation %s: %s", conversation_id, exc)
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail={
                        "error": {
                            "code": "LLM_PROVIDER_ERROR",
                            "message": "The AI service is temporarily unavailable. Your message has been saved as failed and can be retried.",
                            "details": {
                                "failed_message_id": failed_id_str,
                                "retryable": True,
                            },
                        }
                    },
                )

            # 7. Validate output and persist assistant message
            validated_content, _ = self.response_validator.validate(response.content)

            # Transition user message to 'complete' now that generation has actually succeeded!
            user_msg.status = "complete"
            db.add(user_msg)

            context_used_metadata = [
                {
                    "context_id": str(item.id),
                    "title": item.title,
                    "item_type": item.item_type,
                    "version": item.version,
                }
                for item in context_items
            ]

            assistant_msg = msg_repo.create(
                conversation_id=conversation_id,
                role="assistant",
                content=validated_content,
                status="complete",
                provider=response.provider,
                model=response.model,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                context_metadata={
                    "sources": context_used_metadata,
                    "raw": response.raw_metadata,
                },
                commit=False,
            )

            # 8. Deterministic customer-support draft generation for Suggested Actions
            if self._is_draft_eligible(user_msg.content, validated_content):
                # Ensure idempotency: verify an action hasn't already been created for this turn
                existing_action_stmt = select(SuggestedAction).where(
                    SuggestedAction.conversation_id == conversation_id,
                    SuggestedAction.merchant_id == merchant.id,
                    SuggestedAction.payload.op("->>")("user_message_id") == str(user_msg.id),
                )
                existing_action = db.scalars(existing_action_stmt).first()
                if not existing_action:
                    action_repo = ActionRepository(db)
                    action_repo.create(
                        merchant_id=merchant.id,
                        conversation_id=conversation_id,
                        action_type="reply_draft",
                        title=self._generate_action_title(conv.title, user_msg.content),
                        description=validated_content,
                        payload={
                            "generated_reply": validated_content,
                            "user_message_id": str(user_msg.id),
                            "conversation_id": str(conversation_id),
                        },
                        status="pending",
                        created_by="assistant",
                        commit=False,
                    )

            user_msg_response = MessageResponse.model_validate(user_msg)
            assistant_msg_response = MessageResponse.model_validate(assistant_msg)

            # Update last_message_at and commit transaction atomically (releases row lock on success)
            conv.last_message_at = datetime.now(timezone.utc)
            db.add(conv)
            db.commit()

            return ChatResponse(
                user_message=user_msg_response,
                assistant_message=assistant_msg_response,
                context_used=[
                    ContextUsedItem(
                        context_id=item.id,
                        title=item.title,
                        item_type=item.item_type,
                        version=item.version,
                    )
                    for item in context_items
                ],
            )
        except HTTPException:
            # Ensure open transaction and row lock are released on error
            if db.in_transaction():
                db.rollback()
            raise
        except Exception:
            # Ensure open transaction and row lock are released on unhandled exceptions
            if db.in_transaction():
                db.rollback()
            raise
