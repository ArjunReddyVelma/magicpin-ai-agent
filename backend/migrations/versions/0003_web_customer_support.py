"""Add web customer support sessions and messages.

Revision ID: 0003_web_customer_support
Revises: 0002_whatsapp_business_mvp
Create Date: 2026-10-26 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0003_web_customer_support"
down_revision: Union[str, None] = "0002_whatsapp_business_mvp"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. customer_support_sessions
    op.create_table(
        "customer_support_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "merchant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("merchant_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("customer_token_hash", sa.String(length=64), nullable=False),
        sa.Column("customer_name", sa.String(length=120), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
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
        sa.UniqueConstraint(
            "id", "merchant_id", name="uq_customer_support_sessions_id_merchant"
        ),
        sa.CheckConstraint(
            "status IN ('active', 'closed')",
            name="ck_customer_support_sessions_status",
        ),
    )
    op.create_index(
        "ix_customer_support_sessions_merchant_id",
        "customer_support_sessions",
        ["merchant_id"],
    )
    op.create_index(
        "ix_customer_support_sessions_customer_token_hash",
        "customer_support_sessions",
        ["customer_token_hash"],
        unique=True,
    )
    op.create_index(
        "ix_customer_support_sessions_merchant_updated",
        "customer_support_sessions",
        ["merchant_id", "updated_at"],
    )

    # 2. customer_support_messages
    op.create_table(
        "customer_support_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "merchant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("merchant_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("customer_text", sa.Text(), nullable=False),
        sa.Column("suggested_reply", sa.Text(), nullable=True),
        sa.Column("approved_reply", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=24),
            nullable=False,
            server_default=sa.text("'needs_review'"),
        ),
        sa.Column(
            "ai_status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("ai_error", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["session_id", "merchant_id"],
            [
                "customer_support_sessions.id",
                "customer_support_sessions.merchant_id",
            ],
            ondelete="CASCADE",
            name="fk_customer_support_messages_session_merchant",
        ),
        sa.CheckConstraint(
            "status IN ('needs_review', 'delivered', 'dismissed')",
            name="ck_customer_support_messages_status",
        ),
        sa.CheckConstraint(
            "ai_status IN ('pending', 'generating', 'completed', 'failed', 'skipped')",
            name="ck_customer_support_messages_ai_status",
        ),
        sa.CheckConstraint(
            "length(trim(customer_text)) > 0",
            name="ck_customer_support_messages_customer_text_not_empty",
        ),
    )
    op.create_index(
        "ix_customer_support_messages_session_id",
        "customer_support_messages",
        ["session_id"],
    )
    op.create_index(
        "ix_customer_support_messages_merchant_id",
        "customer_support_messages",
        ["merchant_id"],
    )
    op.create_index(
        "ix_csm_session_created",
        "customer_support_messages",
        ["session_id", "created_at"],
    )
    op.create_index(
        "ix_csm_merchant_status_created",
        "customer_support_messages",
        ["merchant_id", "status", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("customer_support_messages")
    op.drop_table("customer_support_sessions")
