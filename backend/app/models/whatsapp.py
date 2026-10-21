import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, DateTime, ForeignKey, func, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from backend.app.db.base import Base

class WhatsAppAccount(Base):
    __tablename__ = "whatsapp_accounts"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("merchant_profiles.id", ondelete="CASCADE"), nullable=False, unique=True)
    phone_number_id: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    business_account_id: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    access_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

class WhatsAppMessage(Base):
    __tablename__ = "whatsapp_messages"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("merchant_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    phone_number_id: Mapped[str] = mapped_column(String(80), nullable=False)
    provider_message_id: Mapped[str] = mapped_column(String(200), nullable=False, unique=True, index=True)
    customer_wa_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    customer_name: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    inbound_text: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_reply: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="needs_review")
    sent_provider_message_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    __table_args__ = (Index("ix_whatsapp_messages_merchant_received", "merchant_id", "received_at"),)
