import uuid
from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    String,
    Text,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    UniqueConstraint,
    CheckConstraint,
    Index,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base
from backend.app.models.merchant_profile import MerchantProfile


class CustomerSupportSession(Base):
    __tablename__ = "customer_support_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    merchant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("merchant_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    customer_token_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    customer_name: Mapped[Optional[str]] = mapped_column(
        String(120), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(20), default="active", nullable=False
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

    __table_args__ = (
        UniqueConstraint("id", "merchant_id", name="uq_customer_support_sessions_id_merchant"),
        CheckConstraint("status IN ('active', 'closed')", name="ck_customer_support_sessions_status"),
        Index("ix_customer_support_sessions_merchant_updated", "merchant_id", "updated_at"),
    )

    # Relationships
    merchant: Mapped["MerchantProfile"] = relationship("MerchantProfile")
    messages: Mapped[List["CustomerSupportMessage"]] = relationship(
        "CustomerSupportMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="CustomerSupportMessage.created_at",
        primaryjoin="and_(CustomerSupportSession.id == CustomerSupportMessage.session_id, CustomerSupportSession.merchant_id == CustomerSupportMessage.merchant_id)",
    )


class CustomerSupportMessage(Base):
    __tablename__ = "customer_support_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    merchant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("merchant_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    customer_text: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_reply: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    approved_reply: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(24), default="needs_review", nullable=False
    )
    ai_status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )
    ai_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    delivered_at: Mapped[Optional[datetime]] = mapped_column(
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

    __table_args__ = (
        ForeignKeyConstraint(
            ["session_id", "merchant_id"],
            ["customer_support_sessions.id", "customer_support_sessions.merchant_id"],
            ondelete="CASCADE",
            name="fk_customer_support_messages_session_merchant",
        ),
        CheckConstraint(
            "status IN ('needs_review', 'delivered', 'dismissed')",
            name="ck_customer_support_messages_status",
        ),
        CheckConstraint(
            "ai_status IN ('pending', 'generating', 'completed', 'failed', 'skipped')",
            name="ck_customer_support_messages_ai_status",
        ),
        CheckConstraint(
            "length(trim(customer_text)) > 0",
            name="ck_customer_support_messages_customer_text_not_empty",
        ),
        Index("ix_csm_session_created", "session_id", "created_at"),
        Index("ix_csm_merchant_status_created", "merchant_id", "status", "created_at"),
    )

    # Relationships
    session: Mapped["CustomerSupportSession"] = relationship(
        "CustomerSupportSession",
        back_populates="messages",
        primaryjoin="and_(CustomerSupportSession.id == CustomerSupportMessage.session_id, CustomerSupportSession.merchant_id == CustomerSupportMessage.merchant_id)",
    )
    merchant: Mapped["MerchantProfile"] = relationship(
        "MerchantProfile",
        foreign_keys=[merchant_id],
        overlaps="messages,session",
    )

    @property
    def customer_name(self) -> Optional[str]:
        return self.session.customer_name if self.session else None
