"""Add functional index for audit_events rate limiting.

Revision ID: 0004_rate_limit_optimization
Revises: 0003_web_customer_support
Create Date: 2026-10-27 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0004_rate_limit_optimization"
down_revision: Union[str, None] = "0003_web_customer_support"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_audit_events_rate_limiting",
        "audit_events",
        [
            "event_type",
            sa.text("(metadata_json ->> 'key')"),
            "created_at",
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_events_rate_limiting", table_name="audit_events")
