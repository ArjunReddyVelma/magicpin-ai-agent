import uuid
from datetime import datetime, timezone
from typing import Optional, List, Tuple, Any
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from backend.app.models.message import Message
from backend.app.repositories.base import BaseRepository


class MessageRepository(BaseRepository):
    def get_by_id(
        self, conversation_id: uuid.UUID, message_id: uuid.UUID
    ) -> Optional[Message]:
        stmt = select(Message).where(
            Message.id == message_id,
            Message.conversation_id == conversation_id,
        )
        return self.db.scalars(stmt).first()

    def list_messages(
        self,
        conversation_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
        before: Optional[datetime] = None,
    ) -> Tuple[List[Message], int]:
        stmt = select(Message).where(Message.conversation_id == conversation_id)

        if before is not None:
            stmt = stmt.where(Message.created_at < before)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = self.db.scalar(count_stmt) or 0

        # Deterministic chronological order
        offset = (page - 1) * page_size
        stmt = (
            stmt.order_by(Message.created_at.asc(), Message.id.asc())
            .offset(offset)
            .limit(page_size)
        )
        messages = list(self.db.scalars(stmt).all())
        return messages, total

    def get_recent_history(
        self, conversation_id: uuid.UUID, limit: int = 20
    ) -> List[Message]:
        """
        Retrieves the most recent N messages, returned in chronological order.
        """
        # Fetch latest 'limit' messages descending
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(limit)
        )
        latest = list(self.db.scalars(stmt).all())
        # Return reversed to restore chronological order
        latest.reverse()
        return latest

    def create(
        self,
        conversation_id: uuid.UUID,
        role: str,
        content: str,
        status: str = "complete",
        provider: Optional[str] = None,
        model: Optional[str] = None,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        context_metadata: Optional[Any] = None,
        created_at: Optional[datetime] = None,
        commit: bool = True,
    ) -> Message:
        message = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            status=status,
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            context_metadata=context_metadata,
            created_at=created_at or datetime.now(timezone.utc),
        )
        self.db.add(message)
        if commit:
            self.db.commit()
            self.db.refresh(message)
        else:
            self.db.flush()
        return message

    def mark_failed(
        self, conversation_id: uuid.UUID, message_id: uuid.UUID
    ) -> Optional[Message]:
        message = self.get_by_id(conversation_id=conversation_id, message_id=message_id)
        if not message:
            return None
        message.status = "failed"
        self.db.commit()
        self.db.refresh(message)
        return message
