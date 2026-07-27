"""Create initial CreatorOS domain models.

Revision ID: 0001
Revises:
Create Date: 2026-07-27
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "channels",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("platform", sa.String(length=20), nullable=False),
        sa.Column("platform_channel_id", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("handle", sa.String(length=255), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "platform IN ('youtube', 'tiktok', 'instagram')",
            name=op.f("ck_channels_platform_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_channels_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_channels"),
        sa.UniqueConstraint(
            "platform",
            "platform_channel_id",
            name="uq_channels_platform_platform_channel_id",
        ),
    )
    op.create_index("ix_channels_user_id", "channels", ["user_id"], unique=False)

    op.create_table(
        "videos",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("platform_video_id", sa.String(length=255), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default=sa.text("'draft'"),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'scheduled', 'published', 'failed')",
            name=op.f("ck_videos_status_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["channel_id"],
            ["channels.id"],
            name="fk_videos_channel_id_channels",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_videos"),
        sa.UniqueConstraint(
            "channel_id",
            "platform_video_id",
            name="uq_videos_channel_id_platform_video_id",
        ),
    )
    op.create_index("ix_videos_channel_id", "videos", ["channel_id"], unique=False)

    op.create_table(
        "video_metrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("video_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("views", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("likes", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("comments", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("shares", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column(
            "watch_time_seconds",
            sa.BigInteger(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "average_view_duration_seconds",
            sa.BigInteger(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("impressions", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column(
            "click_through_rate",
            sa.Numeric(precision=7, scale=4),
            server_default="0",
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["video_id"],
            ["videos.id"],
            name="fk_video_metrics_video_id_videos",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_video_metrics"),
    )
    op.create_index(
        "ix_video_metrics_video_id_captured_at",
        "video_metrics",
        ["video_id", "captured_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_video_metrics_video_id_captured_at",
        table_name="video_metrics",
    )
    op.drop_table("video_metrics")
    op.drop_index("ix_videos_channel_id", table_name="videos")
    op.drop_table("videos")
    op.drop_index("ix_channels_user_id", table_name="channels")
    op.drop_table("channels")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
