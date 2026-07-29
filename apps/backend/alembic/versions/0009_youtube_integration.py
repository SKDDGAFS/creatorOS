"""Add secure OAuth state and platform quota usage.

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-29
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        op.f("ck_video_retention_points_audience_retention_ratio"),
        "video_retention_points",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_video_retention_points_audience_retention_ratio"),
        "video_retention_points",
        "audience_retention_ratio >= 0",
    )

    op.create_table(
        "oauth_authorization_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("platform", sa.String(20), nullable=False),
        sa.Column("state_hash", sa.String(64), nullable=False),
        sa.Column("secret_reference", sa.String(500), nullable=False),
        sa.Column(
            "requested_scopes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("redirect_uri", sa.String(2000), nullable=False),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "consumed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "platform IN ('youtube', 'tiktok', 'instagram')",
            name=op.f("ck_oauth_authorization_states_platform_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_oauth_authorization_states_workspace_id_workspaces",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_oauth_authorization_states_created_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name="pk_oauth_authorization_states",
        ),
    )
    op.create_index(
        "ix_oauth_authorization_states_workspace_id",
        "oauth_authorization_states",
        ["workspace_id"],
    )
    op.create_index(
        "ix_oauth_authorization_states_created_by_user_id",
        "oauth_authorization_states",
        ["created_by_user_id"],
    )
    op.create_index(
        "ix_oauth_authorization_states_platform",
        "oauth_authorization_states",
        ["platform"],
    )
    op.create_index(
        "ix_oauth_authorization_states_state_hash",
        "oauth_authorization_states",
        ["state_hash"],
        unique=True,
    )
    op.create_index(
        "ix_oauth_authorization_states_expires_at",
        "oauth_authorization_states",
        ["expires_at"],
    )

    op.create_table(
        "platform_quota_usage",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "connection_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("usage_date", sa.Date(), nullable=False),
        sa.Column("quota_bucket", sa.String(100), nullable=False),
        sa.Column(
            "units",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "request_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "units >= 0",
            name=op.f("ck_platform_quota_usage_units_nonnegative"),
        ),
        sa.CheckConstraint(
            "request_count >= 0",
            name=op.f("ck_platform_quota_usage_request_count_nonnegative"),
        ),
        sa.ForeignKeyConstraint(
            ["connection_id"],
            ["platform_connections.id"],
            name=("fk_platform_quota_usage_connection_id_platform_connections"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_platform_quota_usage"),
        sa.UniqueConstraint(
            "connection_id",
            "usage_date",
            "quota_bucket",
            name="uq_platform_quota_usage_connection_date_bucket",
        ),
    )
    op.create_index(
        "ix_platform_quota_usage_connection_id",
        "platform_quota_usage",
        ["connection_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_platform_quota_usage_connection_id",
        table_name="platform_quota_usage",
    )
    op.drop_table("platform_quota_usage")

    op.drop_index(
        "ix_oauth_authorization_states_expires_at",
        table_name="oauth_authorization_states",
    )
    op.drop_index(
        "ix_oauth_authorization_states_state_hash",
        table_name="oauth_authorization_states",
    )
    op.drop_index(
        "ix_oauth_authorization_states_platform",
        table_name="oauth_authorization_states",
    )
    op.drop_index(
        "ix_oauth_authorization_states_created_by_user_id",
        table_name="oauth_authorization_states",
    )
    op.drop_index(
        "ix_oauth_authorization_states_workspace_id",
        table_name="oauth_authorization_states",
    )
    op.drop_table("oauth_authorization_states")

    op.drop_constraint(
        op.f("ck_video_retention_points_audience_retention_ratio"),
        "video_retention_points",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_video_retention_points_audience_retention_ratio"),
        "video_retention_points",
        ("audience_retention_ratio >= 0 AND audience_retention_ratio <= 1"),
    )
