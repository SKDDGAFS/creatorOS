"""Add platform account metric snapshots.

Revision ID: 0010
Revises: 0009
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "platform_account_metric_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "connection_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("period", sa.String(30), nullable=False),
        sa.Column(
            "values",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "unavailable_fields",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "provider_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["connection_id"],
            ["platform_connections.id"],
            name=(
                "fk_platform_account_metrics_connection_"
                "platform_connections"
            ),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name="pk_platform_account_metric_snapshots",
        ),
        sa.UniqueConstraint(
            "connection_id",
            "captured_at",
            "period",
            name=(
                "uq_platform_account_metric_snapshots_connection_capture_period"
            ),
        ),
    )
    op.create_index(
        "ix_platform_account_metric_snapshots_connection_id",
        "platform_account_metric_snapshots",
        ["connection_id"],
    )
    op.create_index(
        "ix_platform_account_metric_snapshots_captured_at",
        "platform_account_metric_snapshots",
        ["captured_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_platform_account_metric_snapshots_captured_at",
        table_name="platform_account_metric_snapshots",
    )
    op.drop_index(
        "ix_platform_account_metric_snapshots_connection_id",
        table_name="platform_account_metric_snapshots",
    )
    op.drop_table("platform_account_metric_snapshots")
