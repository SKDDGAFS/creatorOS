"""Add the bounded, durable agent-run framework.

Revision ID: 0013
Revises: 0012
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


OLD_ACTIVITY_TYPES = (
    "'publishing_job_created', 'publishing_state_changed', "
    "'approval_requested', 'approval_approved', 'approval_rejected', "
    "'publishing_scheduled', 'publishing_cancelled', "
    "'publishing_failed', 'publishing_succeeded', "
    "'analytics_sync_scheduled', 'analytics_sync_started', "
    "'analytics_sync_retry_scheduled', 'analytics_sync_failed', "
    "'analytics_sync_succeeded', 'analytics_sync_skipped'"
)
NEW_ACTIVITY_TYPES = (
    f"{OLD_ACTIVITY_TYPES}, 'agent_run_scheduled', 'agent_run_started', "
    "'agent_run_retry_scheduled', 'agent_run_failed', "
    "'agent_run_succeeded', 'agent_run_cancelled'"
)


def upgrade() -> None:
    op.drop_constraint(
        op.f("ck_activity_events_event_type_allowed"),
        "activity_events",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_activity_events_event_type_allowed"),
        "activity_events",
        f"event_type IN ({NEW_ACTIVITY_TYPES})",
    )
    op.create_table(
        "agent_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "requested_by_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "prompt_version_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "durable_job_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "ai_invocation_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("agent_type", sa.String(40), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column(
            "input_references",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(30),
            server_default="queued",
            nullable=False,
        ),
        sa.Column("model_name", sa.String(255), nullable=True),
        sa.Column(
            "estimated_cost_usd",
            sa.Numeric(12, 6),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "output",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("last_error_code", sa.String(100), nullable=True),
        sa.Column("last_error_message", sa.String(500), nullable=True),
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
            "agent_type IN ('content_strategist', 'copywriter', "
            "'social_planner', 'video_analyst', 'token_optimizer')",
            name="ck_agent_runs_agent_type_allowed",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'retry_scheduled', "
            "'succeeded', 'failed', 'cancelled')",
            name="ck_agent_runs_status_allowed",
        ),
        sa.CheckConstraint(
            "estimated_cost_usd >= 0",
            name="ck_agent_runs_estimated_cost_nonnegative",
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_agent_runs_confidence_range",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_agent_runs_workspace_id_workspaces",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"],
            ["users.id"],
            name="fk_agent_runs_requested_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["prompt_version_id"],
            ["ai_prompt_versions.id"],
            name="fk_agent_runs_prompt_version_id_ai_prompt_versions",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["durable_job_id"],
            ["durable_jobs.id"],
            name="fk_agent_runs_durable_job_id_durable_jobs",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ai_invocation_id"],
            ["ai_invocations.id"],
            name="fk_agent_runs_ai_invocation_id_ai_invocations",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_agent_runs"),
        sa.UniqueConstraint(
            "durable_job_id",
            name="uq_agent_runs_durable_job_id",
        ),
        sa.UniqueConstraint(
            "ai_invocation_id",
            name="uq_agent_runs_ai_invocation_id",
        ),
    )
    for column in (
        "workspace_id",
        "requested_by_user_id",
        "prompt_version_id",
        "durable_job_id",
        "ai_invocation_id",
        "agent_type",
        "status",
    ):
        op.create_index(f"ix_agent_runs_{column}", "agent_runs", [column])
    op.create_index(
        "ix_agent_runs_workspace_status_created",
        "agent_runs",
        ["workspace_id", "status", "created_at"],
    )
    op.add_column(
        "activity_events",
        sa.Column("agent_run_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_activity_events_agent_run_id_agent_runs",
        "activity_events",
        "agent_runs",
        ["agent_run_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_activity_events_agent_run_id",
        "activity_events",
        ["agent_run_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_activity_events_agent_run_id", table_name="activity_events")
    op.drop_constraint(
        "fk_activity_events_agent_run_id_agent_runs",
        "activity_events",
        type_="foreignkey",
    )
    op.drop_column("activity_events", "agent_run_id")
    op.drop_index(
        "ix_agent_runs_workspace_status_created",
        table_name="agent_runs",
    )
    for column in (
        "status",
        "agent_type",
        "ai_invocation_id",
        "durable_job_id",
        "prompt_version_id",
        "requested_by_user_id",
        "workspace_id",
    ):
        op.drop_index(f"ix_agent_runs_{column}", table_name="agent_runs")
    op.drop_table("agent_runs")
    op.drop_constraint(
        op.f("ck_activity_events_event_type_allowed"),
        "activity_events",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_activity_events_event_type_allowed"),
        "activity_events",
        f"event_type IN ({OLD_ACTIVITY_TYPES})",
    )
