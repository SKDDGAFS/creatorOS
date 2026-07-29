"""Add PostgreSQL-backed durable jobs and attempt history.

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-29
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "durable_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("job_type", sa.String(100), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "result",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.String(30),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column(
            "priority",
            sa.Integer(),
            server_default=sa.text("50"),
            nullable=False,
        ),
        sa.Column(
            "scheduled_for",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "attempts",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "max_attempts",
            sa.Integer(),
            server_default=sa.text("3"),
            nullable=False,
        ),
        sa.Column("idempotency_key_hash", sa.String(64), nullable=True),
        sa.Column("lock_owner", sa.String(255), nullable=True),
        sa.Column(
            "lock_expires_at",
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
            "started_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "failed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "cancelled_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'retry_scheduled', "
            "'succeeded', 'failed', 'cancelled')",
            name=op.f("ck_durable_jobs_status_allowed"),
        ),
        sa.CheckConstraint(
            "priority >= 0 AND priority <= 100",
            name=op.f("ck_durable_jobs_priority_range"),
        ),
        sa.CheckConstraint(
            "attempts >= 0",
            name=op.f("ck_durable_jobs_attempts_nonnegative"),
        ),
        sa.CheckConstraint(
            "max_attempts >= 1",
            name=op.f("ck_durable_jobs_max_attempts_positive"),
        ),
        sa.CheckConstraint(
            "attempts <= max_attempts",
            name=op.f("ck_durable_jobs_attempts_within_maximum"),
        ),
        sa.CheckConstraint(
            "(lock_owner IS NULL AND lock_expires_at IS NULL) OR "
            "(lock_owner IS NOT NULL AND lock_expires_at IS NOT NULL)",
            name=op.f("ck_durable_jobs_lock_pair_consistent"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_durable_jobs_workspace_id_workspaces",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_durable_jobs_created_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_durable_jobs"),
        sa.UniqueConstraint(
            "workspace_id",
            "job_type",
            "idempotency_key_hash",
            name="uq_durable_jobs_workspace_type_idempotency",
        ),
    )
    op.create_index(
        "ix_durable_jobs_workspace_id",
        "durable_jobs",
        ["workspace_id"],
    )
    op.create_index(
        "ix_durable_jobs_created_by_user_id",
        "durable_jobs",
        ["created_by_user_id"],
    )
    op.create_index(
        "ix_durable_jobs_job_type",
        "durable_jobs",
        ["job_type"],
    )
    op.create_index(
        "ix_durable_jobs_status",
        "durable_jobs",
        ["status"],
    )
    op.create_index(
        "ix_durable_jobs_scheduled_for",
        "durable_jobs",
        ["scheduled_for"],
    )
    op.create_index(
        "ix_durable_jobs_lock_expires_at",
        "durable_jobs",
        ["lock_expires_at"],
    )
    op.create_index(
        "ix_durable_jobs_claim",
        "durable_jobs",
        ["status", "scheduled_for", "priority", "created_at"],
    )

    op.create_table(
        "job_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("worker_id", sa.String(255), nullable=False),
        sa.Column(
            "status",
            sa.String(30),
            server_default=sa.text("'running'"),
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("safe_error_message", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('running', 'succeeded', 'retry_scheduled', "
            "'failed', 'cancelled', 'abandoned')",
            name=op.f("ck_job_attempts_status_allowed"),
        ),
        sa.CheckConstraint(
            "attempt_number >= 1",
            name=op.f("ck_job_attempts_attempt_number_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["durable_jobs.id"],
            name="fk_job_attempts_job_id_durable_jobs",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_job_attempts"),
        sa.UniqueConstraint(
            "job_id",
            "attempt_number",
            name="uq_job_attempts_job_attempt_number",
        ),
    )
    op.create_index(
        "ix_job_attempts_job_id",
        "job_attempts",
        ["job_id"],
    )
    op.create_index(
        "ix_job_attempts_worker_id",
        "job_attempts",
        ["worker_id"],
    )
    op.create_index(
        "ix_job_attempts_status",
        "job_attempts",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_job_attempts_status",
        table_name="job_attempts",
    )
    op.drop_index(
        "ix_job_attempts_worker_id",
        table_name="job_attempts",
    )
    op.drop_index(
        "ix_job_attempts_job_id",
        table_name="job_attempts",
    )
    op.drop_table("job_attempts")

    op.drop_index(
        "ix_durable_jobs_claim",
        table_name="durable_jobs",
    )
    op.drop_index(
        "ix_durable_jobs_lock_expires_at",
        table_name="durable_jobs",
    )
    op.drop_index(
        "ix_durable_jobs_scheduled_for",
        table_name="durable_jobs",
    )
    op.drop_index(
        "ix_durable_jobs_status",
        table_name="durable_jobs",
    )
    op.drop_index(
        "ix_durable_jobs_job_type",
        table_name="durable_jobs",
    )
    op.drop_index(
        "ix_durable_jobs_created_by_user_id",
        table_name="durable_jobs",
    )
    op.drop_index(
        "ix_durable_jobs_workspace_id",
        table_name="durable_jobs",
    )
    op.drop_table("durable_jobs")
