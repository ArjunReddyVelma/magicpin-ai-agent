import uuid
from datetime import datetime, timezone
from typing import Optional, List, Tuple
from sqlalchemy import select, func
from sqlalchemy.orm import Session, joinedload

from backend.app.models.customer_support import (
    CustomerSupportSession,
    CustomerSupportMessage,
)
from backend.app.repositories.base import BaseRepository


class CustomerSupportRepository(BaseRepository):
    def get_session(self, session_id: uuid.UUID) -> Optional[CustomerSupportSession]:
        return self.db.get(CustomerSupportSession, session_id)

    def get_session_by_token_hash(self, token_hash: str) -> Optional[CustomerSupportSession]:
        stmt = select(CustomerSupportSession).where(
            CustomerSupportSession.customer_token_hash == token_hash
        )
        return self.db.scalars(stmt).first()

    def create_session(
        self,
        merchant_id: uuid.UUID,
        customer_token_hash: str,
        customer_name: Optional[str] = None,
        commit: bool = True,
    ) -> CustomerSupportSession:
        session = CustomerSupportSession(
            merchant_id=merchant_id,
            customer_token_hash=customer_token_hash,
            customer_name=customer_name.strip() if customer_name else None,
            status="active",
        )
        self.db.add(session)
        if commit:
            self.db.commit()
            self.db.refresh(session)
        else:
            self.db.flush()
        return session

    def create_message(
        self,
        session_id: uuid.UUID,
        merchant_id: uuid.UUID,
        customer_text: str,
        suggested_reply: Optional[str] = None,
        ai_status: str = "pending",
        ai_error: Optional[str] = None,
        commit: bool = True,
    ) -> CustomerSupportMessage:
        msg = CustomerSupportMessage(
            session_id=session_id,
            merchant_id=merchant_id,
            customer_text=customer_text.strip(),
            suggested_reply=suggested_reply.strip() if suggested_reply else None,
            status="needs_review",
            ai_status=ai_status,
            ai_error=ai_error.strip() if ai_error else None,
        )
        self.db.add(msg)
        if commit:
            self.db.commit()
            self.db.refresh(msg)
        else:
            self.db.flush()
        return msg

    def get_message(
        self, message_id: uuid.UUID, merchant_id: Optional[uuid.UUID] = None
    ) -> Optional[CustomerSupportMessage]:
        stmt = (
            select(CustomerSupportMessage)
            .options(joinedload(CustomerSupportMessage.session))
            .where(CustomerSupportMessage.id == message_id)
        )
        if merchant_id is not None:
            stmt = stmt.where(CustomerSupportMessage.merchant_id == merchant_id)
        return self.db.scalars(stmt).first()

    def get_message_for_update(
        self, message_id: uuid.UUID, merchant_id: Optional[uuid.UUID] = None
    ) -> Optional[CustomerSupportMessage]:
        stmt = (
            select(CustomerSupportMessage)
            .where(CustomerSupportMessage.id == message_id)
            .with_for_update()
        )
        if merchant_id is not None:
            stmt = stmt.where(CustomerSupportMessage.merchant_id == merchant_id)
        return self.db.scalars(stmt).first()

    def list_session_messages(
        self, session_id: uuid.UUID, limit: int = 100
    ) -> List[CustomerSupportMessage]:
        stmt = (
            select(CustomerSupportMessage)
            .where(CustomerSupportMessage.session_id == session_id)
            .order_by(CustomerSupportMessage.created_at.asc(), CustomerSupportMessage.id.asc())
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())

    def list_merchant_messages(
        self,
        merchant_id: uuid.UUID,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[CustomerSupportMessage], int]:
        stmt = (
            select(CustomerSupportMessage)
            .options(joinedload(CustomerSupportMessage.session))
            .where(CustomerSupportMessage.merchant_id == merchant_id)
        )
        if status is not None:
            stmt = stmt.where(CustomerSupportMessage.status == status)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = self.db.scalar(count_stmt) or 0

        offset = (page - 1) * page_size
        stmt = (
            stmt.order_by(
                CustomerSupportMessage.created_at.desc(),
                CustomerSupportMessage.id.asc(),
            )
            .offset(offset)
            .limit(page_size)
        )
        items = list(self.db.scalars(stmt).all())
        return items, total

    def update_suggested_reply(
        self,
        message_id: uuid.UUID,
        merchant_id: uuid.UUID,
        suggested_reply: str,
        commit: bool = True,
    ) -> Optional[CustomerSupportMessage]:
        msg = self.get_message(message_id=message_id, merchant_id=merchant_id)
        if not msg:
            return None
        if msg.status != "needs_review":
            return None

        msg.suggested_reply = suggested_reply.strip()
        msg.updated_at = datetime.now(timezone.utc)
        if commit:
            self.db.commit()
            self.db.refresh(msg)
        else:
            self.db.flush()
        return msg
