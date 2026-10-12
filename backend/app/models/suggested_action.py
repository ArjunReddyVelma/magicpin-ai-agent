import uuid
from datetime import datetime
from typing import Optional, Any
from sqlalchemy import String, DateTime, Text, ForeignKey, func, Index, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base


class SuggestedAction(Base):
    __tablename__ = "suggested_actions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    merchant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("merchant_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    conversation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action_type: Mapped[str] = mapped_column(String(60), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )
    created_by: Mapped[str] = mapped_column(
        String(20), default="assistant", nullable=False
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    merchant: Mapped["MerchantProfile"] = relationship(
        "MerchantProfile", back_populates="suggested_actions"
    )

    __table_args__ = (
        CheckConstraint(
            "action_type IN ('reply_draft', 'summary', 'recommendation', 'follow_up')",
            name="ck_suggested_actions_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'approved', 'dismissed')",
            name="ck_suggested_actions_status",
        ),
        Index("ix_suggested_actions_merchant_status_created", "merchant_id", "status", "created_at"),
    )
