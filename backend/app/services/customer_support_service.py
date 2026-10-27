import hmac
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Tuple
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.app.ai.context_retriever import ContextRetriever
from backend.app.ai.provider import LLMProvider
from backend.app.core.dependencies import get_llm_provider
from backend.app.core.logging import logger
from backend.app.core.security import generate_session_token, hash_session_token
from backend.app.models.customer_support import (
    CustomerSupportSession,
    CustomerSupportMessage,
)
from backend.app.models.merchant_profile import MerchantProfile
from backend.app.repositories.customer_support_repository import CustomerSupportRepository
from backend.app.schemas.customer_support import (
    PublicMerchantProfileResponse,
    CreateCustomerSessionResponse,
    CustomerInquiryResponse,
    CustomerHistoryItem,
    CustomerHistoryResponse,
    MerchantSupportMessageResponse,
    MerchantSupportListResponse,
)


class CustomerSupportService:
    """
    Coordinates public customer support interactions and merchant review workflows.
    Enforces tenant boundaries, token verification, and strict human-in-the-loop AI reply review.
    """

    def __init__(
        self,
        db: Session,
        context_retriever: Optional[ContextRetriever] = None,
        llm_provider: Optional[LLMProvider] = None,
    ):
        self.db = db
        self.context_retriever = context_retriever or ContextRetriever()
        self._llm_provider = llm_provider
        self.repository = CustomerSupportRepository(db)

    def _get_llm_provider(self) -> LLMProvider:
        if self._llm_provider is not None:
            return self._llm_provider
        return get_llm_provider()

    def get_public_merchant_profile(
        self, merchant_id: uuid.UUID
    ) -> PublicMerchantProfileResponse:
        merchant = self.db.get(MerchantProfile, merchant_id)
        if not merchant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": {
                        "code": "MERCHANT_NOT_FOUND",
                        "message": "Merchant not found.",
                    }
                },
            )
        return PublicMerchantProfileResponse(
            merchant_id=merchant.id,
            business_name=merchant.business_name,
            category=merchant.category,
            location=merchant.location,
            description=merchant.description,
        )

    def create_customer_session(
        self, merchant_id: uuid.UUID, customer_name: Optional[str] = None
    ) -> Tuple[CustomerSupportSession, str]:
        merchant = self.db.get(MerchantProfile, merchant_id)
        if not merchant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": {
                        "code": "MERCHANT_NOT_FOUND",
                        "message": "Merchant not found.",
                    }
                },
            )

        raw_token = generate_session_token()
        token_hash = hash_session_token(raw_token)

        session = self.repository.create_session(
            merchant_id=merchant_id,
            customer_token_hash=token_hash,
            customer_name=customer_name,
            commit=True,
        )
        return session, raw_token

    def verify_customer_session(
        self,
        session_id: uuid.UUID,
        customer_token: Optional[str],
        require_active: bool = True,
    ) -> CustomerSupportSession:
        if not customer_token or not customer_token.strip():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error": {
                        "code": "CUSTOMER_TOKEN_REQUIRED",
                        "message": "Customer token is required in X-Customer-Token header.",
                    }
                },
            )

        session = self.repository.get_session(session_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": {
                        "code": "SESSION_NOT_FOUND",
                        "message": "Customer support session not found.",
                    }
                },
            )

        token_hash = hash_session_token(customer_token.strip())
        if not hmac.compare_digest(token_hash, session.customer_token_hash):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": {
                        "code": "INVALID_CUSTOMER_TOKEN",
                        "message": "Invalid customer session token.",
                    }
                },
            )

        if require_active and session.status != "active":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": {
                        "code": "SESSION_CLOSED",
                        "message": "This support session is closed.",
                    }
                },
            )

        return session

    def submit_customer_inquiry(
        self,
        session_id: uuid.UUID,
        customer_token: Optional[str],
        content: str,
    ) -> CustomerSupportMessage:
        session = self.verify_customer_session(session_id, customer_token)

        # 1. Persist inquiry first so it survives any downstream AI failure
        msg = self.repository.create_message(
            session_id=session.id,
            merchant_id=session.merchant_id,
            customer_text=content,
            suggested_reply=None,
            ai_status="pending",
            ai_error=None,
            commit=True,
        )

        # 2. Grounded AI Draft Generation (Strictly human-in-the-loop suggestion)
        try:
            context = self.context_retriever.retrieve_relevant_context(
                merchant_id=session.merchant_id, query=content, db=self.db
            )
            context_blocks = [f"- {item.title}: {item.content}" for item in context]
            context_text = "\n".join(context_blocks)

            merchant = self.db.get(MerchantProfile, session.merchant_id)
            biz_name = merchant.business_name if merchant else "the business"

            prompt = (
                f"You are drafting a reviewable customer support reply for {biz_name}.\n"
                "OPERATING RULES:\n"
                "1. This is a draft proposal for the merchant to review and edit. You cannot and will not send any message directly to the customer.\n"
                "2. Ground your reply strictly in the provided merchant context.\n"
                "3. Never invent prices, availability, delivery timelines, policies, or promises not in the context.\n"
                "4. If context does not have the answer, politely ask a clarifying question or advise contacting the store directly.\n"
                "5. Keep the reply concise (1-3 sentences) and courteous.\n\n"
                f"<merchant_context>\n{context_text or '(No relevant merchant context configured)'}\n</merchant_context>"
            )

            llm = self._get_llm_provider()
            res = llm.generate_response(
                prompt,
                [{"role": "user", "content": content}],
                max_tokens=240,
                temperature=0.3,
            )
            draft = res.content.strip()[:4096] if res and res.content else None
            if draft:
                msg.suggested_reply = draft
                msg.ai_status = "completed"
                msg.ai_error = None
            else:
                msg.suggested_reply = None
                msg.ai_status = "failed"
                msg.ai_error = "AI returned an empty response"
        except Exception as exc:
            logger.error(
                "AI draft generation failed for support message %s: %s", msg.id, exc
            )
            msg.suggested_reply = None
            msg.ai_status = "failed"
            msg.ai_error = str(exc)[:500]

        self.db.commit()
        self.db.refresh(msg)
        return msg

    def get_customer_history(
        self,
        session_id: uuid.UUID,
        customer_token: Optional[str],
        limit: int = 100,
    ) -> CustomerHistoryResponse:
        session = self.verify_customer_session(
            session_id, customer_token, require_active=False
        )
        messages = self.repository.list_session_messages(
            session_id=session.id, limit=limit
        )

        items = [
            CustomerHistoryItem(
                id=m.id,
                customer_text=m.customer_text,
                reply=m.approved_reply if m.status == "delivered" else None,
                status=m.status,
                delivered_at=m.delivered_at,
                created_at=m.created_at,
            )
            for m in messages
        ]
        return CustomerHistoryResponse(
            session_id=session.id,
            items=items,
            total=len(items),
        )

    def list_merchant_messages(
        self,
        merchant_id: uuid.UUID,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> MerchantSupportListResponse:
        messages, total = self.repository.list_merchant_messages(
            merchant_id=merchant_id,
            status=status,
            page=page,
            page_size=page_size,
        )

        items = [
            MerchantSupportMessageResponse(
                id=m.id,
                session_id=m.session_id,
                merchant_id=m.merchant_id,
                customer_name=m.customer_name,
                customer_text=m.customer_text,
                suggested_reply=m.suggested_reply,
                approved_reply=m.approved_reply,
                status=m.status,
                ai_status=m.ai_status,
                ai_error=m.ai_error,
                reviewed_at=m.reviewed_at,
                delivered_at=m.delivered_at,
                created_at=m.created_at,
                updated_at=m.updated_at,
            )
            for m in messages
        ]
        return MerchantSupportListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )

    def edit_merchant_suggested_reply(
        self,
        message_id: uuid.UUID,
        merchant_id: uuid.UUID,
        suggested_reply: str,
    ) -> MerchantSupportMessageResponse:
        msg = self.repository.get_message(
            message_id=message_id, merchant_id=merchant_id
        )
        if not msg:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": {
                        "code": "MESSAGE_NOT_FOUND",
                        "message": "Support message not found.",
                    }
                },
            )

        if msg.status != "needs_review":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": {
                        "code": "MESSAGE_NOT_EDITABLE",
                        "message": "Cannot edit reply for a message that is not in review.",
                    }
                },
            )

        msg.suggested_reply = suggested_reply.strip()
        msg.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(msg)

        return MerchantSupportMessageResponse(
            id=msg.id,
            session_id=msg.session_id,
            merchant_id=msg.merchant_id,
            customer_name=msg.customer_name,
            customer_text=msg.customer_text,
            suggested_reply=msg.suggested_reply,
            approved_reply=msg.approved_reply,
            status=msg.status,
            ai_status=msg.ai_status,
            ai_error=msg.ai_error,
            reviewed_at=msg.reviewed_at,
            delivered_at=msg.delivered_at,
            created_at=msg.created_at,
            updated_at=msg.updated_at,
        )

    def deliver_merchant_reply(
        self,
        message_id: uuid.UUID,
        merchant_id: uuid.UUID,
        reply_text: Optional[str] = None,
    ) -> MerchantSupportMessageResponse:
        msg = self.repository.get_message_for_update(
            message_id=message_id, merchant_id=merchant_id
        )
        if not msg:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": {
                        "code": "MESSAGE_NOT_FOUND",
                        "message": "Support message not found.",
                    }
                },
            )

        if msg.status == "delivered":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": {
                        "code": "MESSAGE_ALREADY_DELIVERED",
                        "message": "This reply has already been delivered.",
                    }
                },
            )

        if msg.status == "dismissed":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": {
                        "code": "MESSAGE_DISMISSED",
                        "message": "Cannot deliver a dismissed message.",
                    }
                },
            )

        if msg.status != "needs_review":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": {
                        "code": "INVALID_STATE",
                        "message": f"Message cannot be delivered in state: {msg.status}",
                    }
                },
            )

        final_text = (
            reply_text.strip()
            if reply_text and reply_text.strip()
            else (msg.suggested_reply.strip() if msg.suggested_reply else None)
        )

        if not final_text:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": {
                        "code": "REPLY_TEXT_REQUIRED",
                        "message": "Reply text cannot be empty or whitespace only.",
                    }
                },
            )

        now = datetime.now(timezone.utc)
        msg.approved_reply = final_text
        msg.status = "delivered"
        msg.reviewed_at = now
        msg.delivered_at = now
        msg.updated_at = now

        self.db.commit()
        self.db.refresh(msg)

        return MerchantSupportMessageResponse(
            id=msg.id,
            session_id=msg.session_id,
            merchant_id=msg.merchant_id,
            customer_name=msg.customer_name,
            customer_text=msg.customer_text,
            suggested_reply=msg.suggested_reply,
            approved_reply=msg.approved_reply,
            status=msg.status,
            ai_status=msg.ai_status,
            ai_error=msg.ai_error,
            reviewed_at=msg.reviewed_at,
            delivered_at=msg.delivered_at,
            created_at=msg.created_at,
            updated_at=msg.updated_at,
        )

    def dismiss_merchant_message(
        self,
        message_id: uuid.UUID,
        merchant_id: uuid.UUID,
    ) -> MerchantSupportMessageResponse:
        msg = self.repository.get_message_for_update(
            message_id=message_id, merchant_id=merchant_id
        )
        if not msg:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": {
                        "code": "MESSAGE_NOT_FOUND",
                        "message": "Support message not found.",
                    }
                },
            )

        if msg.status == "delivered":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": {
                        "code": "MESSAGE_ALREADY_DELIVERED",
                        "message": "Cannot dismiss a message that has already been delivered.",
                    }
                },
            )

        if msg.status == "dismissed":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": {
                        "code": "MESSAGE_ALREADY_DISMISSED",
                        "message": "This message has already been dismissed.",
                    }
                },
            )

        now = datetime.now(timezone.utc)
        msg.status = "dismissed"
        msg.reviewed_at = now
        msg.updated_at = now

        self.db.commit()
        self.db.refresh(msg)

        return MerchantSupportMessageResponse(
            id=msg.id,
            session_id=msg.session_id,
            merchant_id=msg.merchant_id,
            customer_name=msg.customer_name,
            customer_text=msg.customer_text,
            suggested_reply=msg.suggested_reply,
            approved_reply=msg.approved_reply,
            status=msg.status,
            ai_status=msg.ai_status,
            ai_error=msg.ai_error,
            reviewed_at=msg.reviewed_at,
            delivered_at=msg.delivered_at,
            created_at=msg.created_at,
            updated_at=msg.updated_at,
        )
