import uuid
from datetime import datetime
from typing import Optional, List, Tuple
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from backend.app.models.conversation import Conversation
from backend.app.repositories.base import BaseRepository


class ConversationRepository(BaseRepository):
    def get_by_id(
        self, merchant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> Optional[Conversation]:
        stmt = select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.merchant_id == merchant_id,
        )
        return self.db.scalars(stmt).first()

    def list_conversations(
        self,
        merchant_id: uuid.UUID,
        status: Optional[str] = None,
        query: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Conversation], int]:
        stmt = select(Conversation).where(Conversation.merchant_id == merchant_id)

        if status is not None:
            stmt = stmt.where(Conversation.status == status)
        if query:
            clean_q = f"%{query.strip()}%"
            stmt = stmt.where(Conversation.title.ilike(clean_q))

        # Total count
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = self.db.scalar(count_stmt) or 0

        # Deterministic ordering: most recent activity first, tie-break by ID
        offset = (page - 1) * page_size
        activity_time = func.coalesce(Conversation.last_message_at, Conversation.created_at)
        stmt = (
            stmt.order_by(activity_time.desc(), Conversation.id.asc())
            .offset(offset)
            .limit(page_size)
        )
        items = list(self.db.scalars(stmt).all())
        return items, total

    def create(
        self, merchant_id: uuid.UUID, title: str = "New Conversation"
    ) -> Conversation:
        conversation = Conversation(
            merchant_id=merchant_id,
            title=title.strip() if title else "New Conversation",
            status="active",
        )
        self.db.add(conversation)
        self.db.commit()
        self.db.refresh(conversation)
        return conversation

    def update(
        self,
        merchant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        title: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Optional[Conversation]:
        conversation = self.get_by_id(
            merchant_id=merchant_id, conversation_id=conversation_id
        )
        if not conversation:
            return None
        if title is not None:
            conversation.title = title.strip()
        if status is not None:
            conversation.status = status
        self.db.commit()
        self.db.refresh(conversation)
        return conversation

    def update_last_message_at(
        self,
        merchant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        timestamp: Optional[datetime] = None,
    ) -> Optional[Conversation]:
        conversation = self.get_by_id(
            merchant_id=merchant_id, conversation_id=conversation_id
        )
        if not conversation:
            return None
        conversation.last_message_at = timestamp or datetime.utcnow()
        self.db.commit()
        self.db.refresh(conversation)
        return conversation
