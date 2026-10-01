"""Add local media references and manual scheduling queue.

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "channels",
        sa.Column(
            "is_authorized",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "videos", sa.Column("media_path", sa.String(length=500), nullable=True)
    )
    op.add_column(
        "videos", sa.Column("media_mime_type", sa.String(length=100), nullable=True)
    )
    op.add_column(
        "videos", sa.Column("media_size_bytes", sa.BigInteger(), nullable=True)
    )
    op.create_table(
        "scheduled_posts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("video_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recommended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status", sa.String(length=20), server_default="draft", nullable=False
        ),
        sa.Column("metadata", sa.JSON(), server_default="{}", nullable=False),
        sa.Column(
            "timezone", sa.String(length=64), server_default="UTC", nullable=False
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
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_scheduled_posts"),
    )
    op.create_index("ix_scheduled_posts_video_id", "scheduled_posts", ["video_id"])
    op.create_index("ix_scheduled_posts_channel_id", "scheduled_posts", ["channel_id"])
    op.create_index(
        "ix_scheduled_posts_status_scheduled_at",
        "scheduled_posts",
        ["status", "scheduled_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_scheduled_posts_status_scheduled_at", table_name="scheduled_posts"
    )
    op.drop_index("ix_scheduled_posts_channel_id", table_name="scheduled_posts")
    op.drop_index("ix_scheduled_posts_video_id", table_name="scheduled_posts")
    op.drop_table("scheduled_posts")
    op.drop_column("videos", "media_size_bytes")
    op.drop_column("videos", "media_mime_type")
    op.drop_column("videos", "media_path")
    op.drop_column("channels", "is_authorized")
