"""Add analytics synchronization runs and idempotent metric snapshots.

Revision ID: 0011
Revises: 0010
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


OLD_ACTIVITY_TYPES = (
    "'publishing_job_created', 'publishing_state_changed', "
    "'approval_requested', 'approval_approved', 'approval_rejected', "
    "'publishing_scheduled', 'publishing_cancelled', "
    "'publishing_failed', 'publishing_succeeded'"
)
NEW_ACTIVITY_TYPES = (
    f"{OLD_ACTIVITY_TYPES}, 'analytics_sync_scheduled', "
    "'analytics_sync_started', 'analytics_sync_retry_scheduled', "
    "'analytics_sync_failed', 'analytics_sync_succeeded', "
    "'analytics_sync_skipped'"
)


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_video_metrics_video_id_captured_at",
        "video_metrics",
        ["video_id", "captured_at"],
    )
    op.drop_constraint(
        "ck_activity_events_event_type_allowed",
        "activity_events",
        type_="check",
    )
    op.create_check_constraint(
        "ck_activity_events_event_type_allowed",
        "activity_events",
        f"event_type IN ({NEW_ACTIVITY_TYPES})",
    )
    op.create_table(
        "analytics_sync_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("durable_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "status",
            sa.String(30),
            server_default="queued",
            nullable=False,
        ),
        sa.Column(
            "channels_synced",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "videos_synced",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "metrics_synced",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "account_metrics_synced",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "summary",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("last_error_code", sa.String(100), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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
            "status IN ('queued', 'running', 'retry_scheduled', "
            "'succeeded', 'failed', 'skipped')",
            name="ck_analytics_sync_runs_status_allowed",
        ),
        sa.CheckConstraint(
            "channels_synced >= 0",
            name="ck_analytics_sync_runs_channels_synced_nonnegative",
        ),
        sa.CheckConstraint(
            "videos_synced >= 0",
            name="ck_analytics_sync_runs_videos_synced_nonnegative",
        ),
        sa.CheckConstraint(
            "metrics_synced >= 0",
            name="ck_analytics_sync_runs_metrics_synced_nonnegative",
        ),
        sa.CheckConstraint(
            "account_metrics_synced >= 0",
            name="ck_analytics_sync_runs_account_metrics_synced_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_analytics_sync_runs_workspace_id_workspaces",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["connection_id"],
            ["platform_connections.id"],
            name="fk_analytics_sync_runs_connection_id_platform_connections",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["durable_job_id"],
            ["durable_jobs.id"],
            name="fk_analytics_sync_runs_durable_job_id_durable_jobs",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_analytics_sync_runs"),
        sa.UniqueConstraint(
            "durable_job_id",
            name="uq_analytics_sync_runs_durable_job_id",
        ),
    )
    op.create_index(
        "ix_analytics_sync_runs_workspace_id",
        "analytics_sync_runs",
        ["workspace_id"],
    )
    op.create_index(
        "ix_analytics_sync_runs_connection_id",
        "analytics_sync_runs",
        ["connection_id"],
    )
    op.create_index(
        "ix_analytics_sync_runs_durable_job_id",
        "analytics_sync_runs",
        ["durable_job_id"],
    )
    op.create_index(
        "ix_analytics_sync_runs_status",
        "analytics_sync_runs",
        ["status"],
    )
    op.create_index(
        "ix_analytics_sync_runs_workspace_status_created",
        "analytics_sync_runs",
        ["workspace_id", "status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_analytics_sync_runs_workspace_status_created",
        table_name="analytics_sync_runs",
    )
    op.drop_index(
        "ix_analytics_sync_runs_status",
        table_name="analytics_sync_runs",
    )
    op.drop_index(
        "ix_analytics_sync_runs_durable_job_id",
        table_name="analytics_sync_runs",
    )
    op.drop_index(
        "ix_analytics_sync_runs_connection_id",
        table_name="analytics_sync_runs",
    )
    op.drop_index(
        "ix_analytics_sync_runs_workspace_id",
        table_name="analytics_sync_runs",
    )
    op.drop_table("analytics_sync_runs")
    op.drop_constraint(
        "ck_activity_events_event_type_allowed",
        "activity_events",
        type_="check",
    )
    op.create_check_constraint(
        "ck_activity_events_event_type_allowed",
        "activity_events",
        f"event_type IN ({OLD_ACTIVITY_TYPES})",
    )
    op.drop_constraint(
        "uq_video_metrics_video_id_captured_at",
        "video_metrics",
        type_="unique",
    )
