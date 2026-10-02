"""Add separate connected social accounts.

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("platform", sa.String(length=20), nullable=False),
        sa.Column("account_name", sa.String(length=255), nullable=False),
        sa.Column("channel_id", sa.String(length=255), nullable=True),
        sa.Column("is_connected", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("oauth_state", sa.Text(), nullable=True),
        sa.Column("scopes", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("access_token", sa.Text(), nullable=True),
        sa.Column("refresh_token", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=1000), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "platform IN ('youtube', 'tiktok', 'instagram')",
            name="platform_allowed",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_accounts"),
        sa.UniqueConstraint(
            "user_id",
            "platform",
            "channel_id",
            name="uq_accounts_user_platform_channel",
        ),
    )
    op.create_index("ix_accounts_user_id", "accounts", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_accounts_user_id", table_name="accounts")
    op.drop_table("accounts")
