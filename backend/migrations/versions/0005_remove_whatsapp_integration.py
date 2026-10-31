"""Remove WhatsApp and Meta integration tables.

Revision ID: 0005_remove_whatsapp_integration
Revises: 0004_rate_limit_optimization
Create Date: 2026-10-31 12:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0005_remove_whatsapp_integration"
down_revision: Union[str, None] = "0004_rate_limit_optimization"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("whatsapp_messages")
    op.drop_table("whatsapp_accounts")


def downgrade() -> None:
    op.create_table(
        "whatsapp_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "merchant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("merchant_profiles.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("phone_number_id", sa.String(80), nullable=False, unique=True),
        sa.Column("business_account_id", sa.String(80), nullable=True),
        sa.Column("access_token_encrypted", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_table(
        "whatsapp_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "merchant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("merchant_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("phone_number_id", sa.String(80), nullable=False),
        sa.Column("provider_message_id", sa.String(200), nullable=False),
        sa.Column("customer_wa_id", sa.String(80), nullable=False),
        sa.Column("customer_name", sa.String(160), nullable=True),
        sa.Column("inbound_text", sa.Text(), nullable=False),
        sa.Column("suggested_reply", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "status",
            sa.String(24),
            nullable=False,
            server_default="needs_review",
        ),
        sa.Column("sent_provider_message_id", sa.String(200), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_whatsapp_messages_merchant_id", "whatsapp_messages", ["merchant_id"]
    )
    op.create_index(
        "ix_whatsapp_messages_provider_message_id",
        "whatsapp_messages",
        ["provider_message_id"],
        unique=True,
    )
    op.create_index(
        "ix_whatsapp_messages_customer_wa_id", "whatsapp_messages", ["customer_wa_id"]
    )
    op.create_index(
        "ix_whatsapp_messages_merchant_received",
        "whatsapp_messages",
        ["merchant_id", "received_at"],
    )
