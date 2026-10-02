"""Persist local video preparation output.

Revision ID: 0005
Revises: 0004
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("videos", sa.Column("transcript", sa.Text(), nullable=True))
    op.add_column("videos", sa.Column("ai_analysis", sa.JSON(), nullable=True))
    op.add_column("videos", sa.Column("draft_metadata", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("videos", "draft_metadata")
    op.drop_column("videos", "ai_analysis")
    op.drop_column("videos", "transcript")
