"""Add research sources, runs, findings, evidence, hooks, and ideas.

Revision ID: 0014
Revises: 0013
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_ACTIVITY_TYPES = (
    "'publishing_job_created', 'publishing_state_changed', "
    "'approval_requested', 'approval_approved', 'approval_rejected', "
    "'publishing_scheduled', 'publishing_cancelled', "
    "'publishing_failed', 'publishing_succeeded', "
    "'analytics_sync_scheduled', 'analytics_sync_started', "
    "'analytics_sync_retry_scheduled', 'analytics_sync_failed', "
    "'analytics_sync_succeeded', 'analytics_sync_skipped', "
    "'agent_run_scheduled', 'agent_run_started', "
    "'agent_run_retry_scheduled', 'agent_run_failed', "
    "'agent_run_succeeded', 'agent_run_cancelled'"
)
NEW_ACTIVITY_TYPES = (
    f"{OLD_ACTIVITY_TYPES}, 'research_run_scheduled', 'research_run_started', "
    "'research_run_retry_scheduled', 'research_run_failed', "
    "'research_run_succeeded', 'research_run_cancelled'"
)


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
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
        "research_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_type", sa.String(30), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("canonical_url", sa.String(2048), nullable=True),
        sa.Column("publisher", sa.String(255), nullable=True),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("source_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "retrieved_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "stale_after_days", sa.Integer(), server_default="30", nullable=False
        ),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("source_metadata", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source_type IN ('official_api', 'public_web', 'first_party', 'manual')",
            name=op.f("ck_research_sources_source_type_allowed"),
        ),
        sa.CheckConstraint(
            "stale_after_days >= 1 AND stale_after_days <= 3650",
            name=op.f("ck_research_sources_stale_after_days_range"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "content_hash",
            name="uq_research_sources_workspace_content_hash",
        ),
    )
    for column in ("workspace_id", "created_by_user_id", "source_type", "source_date"):
        op.create_index(f"ix_research_sources_{column}", "research_sources", [column])

    op.create_table(
        "competitors",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("platform", sa.String(20), nullable=False),
        sa.Column("handle", sa.String(255), nullable=False),
        sa.Column("profile_url", sa.String(2048), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        *_timestamps(),
        sa.CheckConstraint(
            "platform IN ('youtube', 'instagram', 'tiktok')",
            name=op.f("ck_competitors_platform_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "platform",
            "handle",
            name="uq_competitors_workspace_platform_handle",
        ),
    )
    for column in ("workspace_id", "created_by_user_id", "platform", "is_active"):
        op.create_index(f"ix_competitors_{column}", "competitors", [column])

    op.create_table(
        "research_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("prompt_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("durable_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ai_invocation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("source_ids", postgresql.JSONB(), nullable=False),
        sa.Column("competitor_ids", postgresql.JSONB(), nullable=False),
        sa.Column(
            "include_stale_sources",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("status", sa.String(30), server_default="queued", nullable=False),
        sa.Column("model_name", sa.String(255), nullable=True),
        sa.Column(
            "estimated_cost_usd",
            sa.Numeric(12, 6),
            server_default="0",
            nullable=False,
        ),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column(
            "fresh_source_count", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column(
            "stale_source_count", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column("last_error_code", sa.String(100), nullable=True),
        sa.Column("last_error_message", sa.String(500), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'retry_scheduled', "
            "'succeeded', 'failed', 'cancelled')",
            name=op.f("ck_research_runs_status_allowed"),
        ),
        sa.CheckConstraint(
            "fresh_source_count >= 0",
            name=op.f("ck_research_runs_fresh_sources_nonnegative"),
        ),
        sa.CheckConstraint(
            "stale_source_count >= 0",
            name=op.f("ck_research_runs_stale_sources_nonnegative"),
        ),
        sa.CheckConstraint(
            "estimated_cost_usd >= 0",
            name=op.f("ck_research_runs_cost_nonnegative"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["prompt_version_id"], ["ai_prompt_versions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["durable_job_id"], ["durable_jobs.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["ai_invocation_id"], ["ai_invocations.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("durable_job_id", name="uq_research_runs_durable_job_id"),
        sa.UniqueConstraint(
            "ai_invocation_id", name="uq_research_runs_ai_invocation_id"
        ),
    )
    run_indexes = (
        "workspace_id",
        "requested_by_user_id",
        "prompt_version_id",
        "durable_job_id",
        "ai_invocation_id",
        "status",
    )
    for column in run_indexes:
        op.create_index(f"ix_research_runs_{column}", "research_runs", [column])
    op.create_index(
        "ix_research_runs_workspace_status_created",
        "research_runs",
        ["workspace_id", "status", "created_at"],
    )

    op.create_table(
        "research_findings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("first_seen_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("last_seen_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("finding_type", sa.String(30), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("source_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("freshness_status", sa.String(20), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "finding_type IN ('trend', 'content_pattern')",
            name=op.f("ck_research_findings_finding_type_allowed"),
        ),
        sa.CheckConstraint(
            "freshness_status IN ('current', 'stale')",
            name=op.f("ck_research_findings_freshness_status_allowed"),
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name=op.f("ck_research_findings_confidence_range"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["first_seen_run_id"], ["research_runs.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["last_seen_run_id"], ["research_runs.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "fingerprint",
            name="uq_research_findings_workspace_fingerprint",
        ),
    )
    finding_indexes = (
        "workspace_id",
        "first_seen_run_id",
        "last_seen_run_id",
        "finding_type",
        "source_date",
        "freshness_status",
    )
    for column in finding_indexes:
        op.create_index(f"ix_research_findings_{column}", "research_findings", [column])

    for table_name, text_column in (
        ("research_hooks", "text"),
        ("content_ideas", "title"),
    ):
        columns: list[sa.Column] = [
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column(
                "first_seen_run_id", postgresql.UUID(as_uuid=True), nullable=False
            ),
            sa.Column(
                "last_seen_run_id", postgresql.UUID(as_uuid=True), nullable=False
            ),
            sa.Column(
                text_column,
                sa.String(1000 if table_name == "research_hooks" else 500),
                nullable=False,
            ),
        ]
        if table_name == "research_hooks":
            columns.extend(
                [
                    sa.Column("rationale", sa.String(2000), nullable=False),
                    sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
                    sa.Column("source_ids", postgresql.JSONB(), nullable=False),
                ]
            )
        else:
            columns.extend(
                [
                    sa.Column("concept", sa.Text(), nullable=False),
                    sa.Column("suggested_hook", sa.String(1000), nullable=True),
                    sa.Column("platforms", postgresql.JSONB(), nullable=False),
                    sa.Column("source_ids", postgresql.JSONB(), nullable=False),
                    sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
                ]
            )
        columns.extend(
            [
                sa.Column("fingerprint", sa.String(64), nullable=False),
                sa.Column(
                    "first_seen_at",
                    sa.DateTime(timezone=True),
                    server_default=sa.text("now()"),
                    nullable=False,
                ),
                sa.Column(
                    "last_seen_at",
                    sa.DateTime(timezone=True),
                    server_default=sa.text("now()"),
                    nullable=False,
                ),
            ]
        )
        op.create_table(
            table_name,
            *columns,
            sa.CheckConstraint(
                "confidence >= 0 AND confidence <= 1",
                name=op.f(f"ck_{table_name}_confidence_range"),
            ),
            sa.ForeignKeyConstraint(
                ["workspace_id"], ["workspaces.id"], ondelete="RESTRICT"
            ),
            sa.ForeignKeyConstraint(
                ["first_seen_run_id"], ["research_runs.id"], ondelete="RESTRICT"
            ),
            sa.ForeignKeyConstraint(
                ["last_seen_run_id"], ["research_runs.id"], ondelete="RESTRICT"
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "workspace_id",
                "fingerprint",
                name=f"uq_{table_name}_workspace_fingerprint",
            ),
        )
        for column in ("workspace_id", "first_seen_run_id", "last_seen_run_id"):
            op.create_index(f"ix_{table_name}_{column}", table_name, [column])

    op.create_table(
        "research_finding_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("finding_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_note", sa.String(1000), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["finding_id"], ["research_findings.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["source_id"], ["research_sources.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "finding_id", "source_id", name="uq_research_finding_evidence_pair"
        ),
    )
    for column in ("finding_id", "source_id"):
        op.create_index(
            f"ix_research_finding_evidence_{column}",
            "research_finding_evidence",
            [column],
        )

    op.add_column(
        "activity_events",
        sa.Column("research_run_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_activity_events_research_run_id_research_runs",
        "activity_events",
        "research_runs",
        ["research_run_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_activity_events_research_run_id", "activity_events", ["research_run_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_activity_events_research_run_id", table_name="activity_events")
    op.drop_constraint(
        "fk_activity_events_research_run_id_research_runs",
        "activity_events",
        type_="foreignkey",
    )
    op.drop_column("activity_events", "research_run_id")
    for table_name, indexes in (
        ("research_finding_evidence", ("source_id", "finding_id")),
        ("content_ideas", ("last_seen_run_id", "first_seen_run_id", "workspace_id")),
        ("research_hooks", ("last_seen_run_id", "first_seen_run_id", "workspace_id")),
        (
            "research_findings",
            (
                "freshness_status",
                "source_date",
                "finding_type",
                "last_seen_run_id",
                "first_seen_run_id",
                "workspace_id",
            ),
        ),
    ):
        for column in indexes:
            op.drop_index(f"ix_{table_name}_{column}", table_name=table_name)
        op.drop_table(table_name)
    op.drop_index(
        "ix_research_runs_workspace_status_created", table_name="research_runs"
    )
    for column in reversed(
        (
            "workspace_id",
            "requested_by_user_id",
            "prompt_version_id",
            "durable_job_id",
            "ai_invocation_id",
            "status",
        )
    ):
        op.drop_index(f"ix_research_runs_{column}", table_name="research_runs")
    op.drop_table("research_runs")
    for table_name, columns in (
        (
            "competitors",
            ("is_active", "platform", "created_by_user_id", "workspace_id"),
        ),
        (
            "research_sources",
            ("source_date", "source_type", "created_by_user_id", "workspace_id"),
        ),
    ):
        for column in columns:
            op.drop_index(f"ix_{table_name}_{column}", table_name=table_name)
        op.drop_table(table_name)
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
