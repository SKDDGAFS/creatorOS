"""Add publishing workflow, approvals, transitions, and activity events.

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-29
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PUBLISHING_STATES = (
    "'draft', 'preparing', 'awaiting_approval', 'approved', 'scheduled', "
    "'publishing', 'published', 'rejected', 'failed', 'cancelled'"
)


def upgrade() -> None:
    op.create_table(
        "publishing_jobs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "video_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("idempotency_key_hash", sa.String(64), nullable=False),
        sa.Column(
            "status",
            sa.String(30),
            server_default=sa.text("'draft'"),
            nullable=False,
        ),
        sa.Column(
            "scheduled_for",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "approved_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "cancelled_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "failed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("last_error_code", sa.String(100), nullable=True),
        sa.Column("last_error_message", sa.String(500), nullable=True),
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
            f"status IN ({PUBLISHING_STATES})",
            name=op.f("ck_publishing_jobs_status_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_publishing_jobs_workspace_id_workspaces",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["video_id"],
            ["videos.id"],
            name="fk_publishing_jobs_video_id_videos",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_publishing_jobs_created_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_publishing_jobs"),
        sa.UniqueConstraint(
            "workspace_id",
            "idempotency_key_hash",
            name="uq_publishing_jobs_workspace_idempotency_key",
        ),
    )
    op.create_index(
        "ix_publishing_jobs_workspace_id",
        "publishing_jobs",
        ["workspace_id"],
    )
    op.create_index(
        "ix_publishing_jobs_video_id",
        "publishing_jobs",
        ["video_id"],
    )
    op.create_index(
        "ix_publishing_jobs_created_by_user_id",
        "publishing_jobs",
        ["created_by_user_id"],
    )
    op.create_index(
        "ix_publishing_jobs_status",
        "publishing_jobs",
        ["status"],
    )
    op.create_index(
        "ix_publishing_jobs_scheduled_for",
        "publishing_jobs",
        ["scheduled_for"],
    )

    op.create_table(
        "approval_requests",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "publishing_job_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "requested_by_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "decided_by_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("request_note", sa.Text(), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "decided_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'cancelled')",
            name=op.f("ck_approval_requests_status_allowed"),
        ),
        sa.CheckConstraint(
            "sequence >= 1",
            name=op.f("ck_approval_requests_sequence_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["publishing_job_id"],
            ["publishing_jobs.id"],
            name="fk_approval_requests_publishing_job_id_publishing_jobs",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"],
            ["users.id"],
            name="fk_approval_requests_requested_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["decided_by_user_id"],
            ["users.id"],
            name="fk_approval_requests_decided_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_approval_requests"),
        sa.UniqueConstraint(
            "publishing_job_id",
            "sequence",
            name="uq_approval_requests_job_sequence",
        ),
    )
    op.create_index(
        "ix_approval_requests_publishing_job_id",
        "approval_requests",
        ["publishing_job_id"],
    )
    op.create_index(
        "ix_approval_requests_requested_by_user_id",
        "approval_requests",
        ["requested_by_user_id"],
    )
    op.create_index(
        "ix_approval_requests_decided_by_user_id",
        "approval_requests",
        ["decided_by_user_id"],
    )
    op.create_index(
        "ix_approval_requests_status",
        "approval_requests",
        ["status"],
    )

    op.create_table(
        "publishing_transitions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "publishing_job_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "actor_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("from_state", sa.String(30), nullable=True),
        sa.Column("to_state", sa.String(30), nullable=False),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            f"from_state IS NULL OR from_state IN ({PUBLISHING_STATES})",
            name=op.f("ck_publishing_transitions_from_state_allowed"),
        ),
        sa.CheckConstraint(
            f"to_state IN ({PUBLISHING_STATES})",
            name=op.f("ck_publishing_transitions_to_state_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["publishing_job_id"],
            ["publishing_jobs.id"],
            name=(
                "fk_publishing_transitions_publishing_job_id_"
                "publishing_jobs"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name="fk_publishing_transitions_actor_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_publishing_transitions"),
    )
    op.create_index(
        "ix_publishing_transitions_publishing_job_id",
        "publishing_transitions",
        ["publishing_job_id"],
    )
    op.create_index(
        "ix_publishing_transitions_actor_user_id",
        "publishing_transitions",
        ["actor_user_id"],
    )

    op.create_table(
        "activity_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "actor_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "publishing_job_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("event_type", sa.String(60), nullable=False),
        sa.Column(
            "event_data",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "event_type IN "
            "('publishing_job_created', 'publishing_state_changed', "
            "'approval_requested', 'approval_approved', "
            "'approval_rejected', 'publishing_scheduled', "
            "'publishing_cancelled', 'publishing_failed', "
            "'publishing_succeeded')",
            name=op.f("ck_activity_events_event_type_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_activity_events_workspace_id_workspaces",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name="fk_activity_events_actor_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["publishing_job_id"],
            ["publishing_jobs.id"],
            name="fk_activity_events_publishing_job_id_publishing_jobs",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_activity_events"),
    )
    op.create_index(
        "ix_activity_events_workspace_id",
        "activity_events",
        ["workspace_id"],
    )
    op.create_index(
        "ix_activity_events_actor_user_id",
        "activity_events",
        ["actor_user_id"],
    )
    op.create_index(
        "ix_activity_events_publishing_job_id",
        "activity_events",
        ["publishing_job_id"],
    )
    op.create_index(
        "ix_activity_events_event_type",
        "activity_events",
        ["event_type"],
    )
    op.create_index(
        "ix_activity_events_created_at",
        "activity_events",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_activity_events_created_at",
        table_name="activity_events",
    )
    op.drop_index(
        "ix_activity_events_event_type",
        table_name="activity_events",
    )
    op.drop_index(
        "ix_activity_events_publishing_job_id",
        table_name="activity_events",
    )
    op.drop_index(
        "ix_activity_events_actor_user_id",
        table_name="activity_events",
    )
    op.drop_index(
        "ix_activity_events_workspace_id",
        table_name="activity_events",
    )
    op.drop_table("activity_events")

    op.drop_index(
        "ix_publishing_transitions_actor_user_id",
        table_name="publishing_transitions",
    )
    op.drop_index(
        "ix_publishing_transitions_publishing_job_id",
        table_name="publishing_transitions",
    )
    op.drop_table("publishing_transitions")

    op.drop_index(
        "ix_approval_requests_status",
        table_name="approval_requests",
    )
    op.drop_index(
        "ix_approval_requests_decided_by_user_id",
        table_name="approval_requests",
    )
    op.drop_index(
        "ix_approval_requests_requested_by_user_id",
        table_name="approval_requests",
    )
    op.drop_index(
        "ix_approval_requests_publishing_job_id",
        table_name="approval_requests",
    )
    op.drop_table("approval_requests")

    op.drop_index(
        "ix_publishing_jobs_scheduled_for",
        table_name="publishing_jobs",
    )
    op.drop_index(
        "ix_publishing_jobs_status",
        table_name="publishing_jobs",
    )
    op.drop_index(
        "ix_publishing_jobs_created_by_user_id",
        table_name="publishing_jobs",
    )
    op.drop_index(
        "ix_publishing_jobs_video_id",
        table_name="publishing_jobs",
    )
    op.drop_index(
        "ix_publishing_jobs_workspace_id",
        table_name="publishing_jobs",
    )
    op.drop_table("publishing_jobs")
