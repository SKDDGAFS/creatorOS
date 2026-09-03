"""Add AI provider routing, prompts, budgets, and usage records.

Revision ID: 0012
Revises: 0011
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_provider_configurations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("provider_kind", sa.String(30), nullable=False),
        sa.Column("base_url", sa.String(2048), nullable=False),
        sa.Column("model_name", sa.String(255), nullable=False),
        sa.Column("credential_reference", sa.String(255), nullable=True),
        sa.Column(
            "capability_tier",
            sa.String(30),
            server_default="lightweight",
            nullable=False,
        ),
        sa.Column("priority", sa.Integer(), server_default="50", nullable=False),
        sa.Column("timeout_seconds", sa.Numeric(8, 3), nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="2", nullable=False),
        sa.Column(
            "input_cost_per_million",
            sa.Numeric(12, 6),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "output_cost_per_million",
            sa.Numeric(12, 6),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "is_enabled",
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
            "provider_kind IN ('ollama', 'openai_compatible')",
            name="ck_ai_provider_configurations_provider_kind_allowed",
        ),
        sa.CheckConstraint(
            "capability_tier IN ('lightweight', 'standard', 'advanced')",
            name="ck_ai_provider_configurations_capability_tier_allowed",
        ),
        sa.CheckConstraint(
            "priority >= 0 AND priority <= 100",
            name="ck_ai_provider_configurations_priority_range",
        ),
        sa.CheckConstraint(
            "timeout_seconds > 0 AND timeout_seconds <= 300",
            name="ck_ai_provider_configurations_timeout_seconds_range",
        ),
        sa.CheckConstraint(
            "max_attempts >= 1 AND max_attempts <= 5",
            name="ck_ai_provider_configurations_max_attempts_range",
        ),
        sa.CheckConstraint(
            "input_cost_per_million >= 0",
            name="ck_ai_provider_configurations_input_cost_nonnegative",
        ),
        sa.CheckConstraint(
            "output_cost_per_million >= 0",
            name="ck_ai_provider_configurations_output_cost_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_ai_provider_configurations_workspace_id_workspaces",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_ai_provider_configurations_created_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ai_provider_configurations"),
        sa.UniqueConstraint(
            "workspace_id",
            "name",
            name="uq_ai_provider_configurations_workspace_name",
        ),
    )
    op.create_index(
        "ix_ai_provider_configurations_workspace_id",
        "ai_provider_configurations",
        ["workspace_id"],
    )
    op.create_index(
        "ix_ai_provider_configurations_created_by_user_id",
        "ai_provider_configurations",
        ["created_by_user_id"],
    )
    op.create_index(
        "ix_ai_provider_configurations_provider_kind",
        "ai_provider_configurations",
        ["provider_kind"],
    )
    op.create_index(
        "ix_ai_provider_configurations_capability_tier",
        "ai_provider_configurations",
        ["capability_tier"],
    )
    op.create_index(
        "ix_ai_provider_configurations_is_enabled",
        "ai_provider_configurations",
        ["is_enabled"],
    )
    op.create_index(
        "ix_ai_provider_configurations_selection",
        "ai_provider_configurations",
        ["workspace_id", "is_enabled", "priority"],
    )

    op.create_table(
        "ai_prompt_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("system_template", sa.Text(), nullable=False),
        sa.Column("user_template", sa.Text(), nullable=False),
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
        sa.CheckConstraint(
            "version >= 1",
            name="ck_ai_prompt_versions_version_positive",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_ai_prompt_versions_workspace_id_workspaces",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_ai_prompt_versions_created_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ai_prompt_versions"),
        sa.UniqueConstraint(
            "workspace_id",
            "name",
            "version",
            name="uq_ai_prompt_versions_workspace_name_version",
        ),
    )
    op.create_index(
        "ix_ai_prompt_versions_workspace_id",
        "ai_prompt_versions",
        ["workspace_id"],
    )
    op.create_index(
        "ix_ai_prompt_versions_created_by_user_id",
        "ai_prompt_versions",
        ["created_by_user_id"],
    )
    op.create_index(
        "ix_ai_prompt_versions_is_active",
        "ai_prompt_versions",
        ["is_active"],
    )
    op.create_index(
        "ix_ai_prompt_versions_lookup",
        "ai_prompt_versions",
        ["workspace_id", "name", "is_active", "version"],
    )
    op.create_index(
        "uq_ai_prompt_versions_active_name",
        "ai_prompt_versions",
        ["workspace_id", "name"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )

    op.create_table(
        "ai_usage_budgets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("monthly_token_limit", sa.Integer(), nullable=True),
        sa.Column("monthly_cost_limit_usd", sa.Numeric(12, 6), nullable=True),
        sa.Column(
            "default_max_output_tokens",
            sa.Integer(),
            server_default="2048",
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
            "monthly_token_limit IS NULL OR monthly_token_limit > 0",
            name="ck_ai_usage_budgets_monthly_token_limit_positive",
        ),
        sa.CheckConstraint(
            "monthly_cost_limit_usd IS NULL OR monthly_cost_limit_usd > 0",
            name="ck_ai_usage_budgets_monthly_cost_limit_positive",
        ),
        sa.CheckConstraint(
            "default_max_output_tokens >= 1 AND default_max_output_tokens <= 32768",
            name="ck_ai_usage_budgets_default_max_output_tokens_range",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_ai_usage_budgets_workspace_id_workspaces",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ai_usage_budgets"),
        sa.UniqueConstraint(
            "workspace_id",
            name="uq_ai_usage_budgets_workspace_id",
        ),
    )
    op.create_index(
        "ix_ai_usage_budgets_workspace_id",
        "ai_usage_budgets",
        ["workspace_id"],
    )

    op.create_table(
        "ai_invocations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "provider_configuration_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "prompt_version_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "requested_by_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("idempotency_key_hash", sa.String(64), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("provider_kind", sa.String(30), nullable=False),
        sa.Column("model_name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("output_tokens", sa.Integer(), server_default="0", nullable=False),
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
        sa.Column("last_error_code", sa.String(100), nullable=True),
        sa.Column("last_error_message", sa.String(500), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('succeeded', 'failed')",
            name="ck_ai_invocations_status_allowed",
        ),
        sa.CheckConstraint(
            "attempts >= 1",
            name="ck_ai_invocations_attempts_positive",
        ),
        sa.CheckConstraint(
            "input_tokens >= 0",
            name="ck_ai_invocations_input_tokens_nonnegative",
        ),
        sa.CheckConstraint(
            "output_tokens >= 0",
            name="ck_ai_invocations_output_tokens_nonnegative",
        ),
        sa.CheckConstraint(
            "estimated_cost_usd >= 0",
            name="ck_ai_invocations_cost_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_ai_invocations_workspace_id_workspaces",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["provider_configuration_id"],
            ["ai_provider_configurations.id"],
            name="fk_ai_invocations_provider_config_ai_providers",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["prompt_version_id"],
            ["ai_prompt_versions.id"],
            name="fk_ai_invocations_prompt_version_id_ai_prompt_versions",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"],
            ["users.id"],
            name="fk_ai_invocations_requested_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ai_invocations"),
        sa.UniqueConstraint(
            "workspace_id",
            "idempotency_key_hash",
            name="uq_ai_invocations_workspace_idempotency",
        ),
    )
    for column in (
        "workspace_id",
        "provider_configuration_id",
        "prompt_version_id",
        "requested_by_user_id",
        "status",
    ):
        op.create_index(
            f"ix_ai_invocations_{column}",
            "ai_invocations",
            [column],
        )
    op.create_index(
        "ix_ai_invocations_workspace_created",
        "ai_invocations",
        ["workspace_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_invocations_workspace_created",
        table_name="ai_invocations",
    )
    for column in (
        "status",
        "requested_by_user_id",
        "prompt_version_id",
        "provider_configuration_id",
        "workspace_id",
    ):
        op.drop_index(f"ix_ai_invocations_{column}", table_name="ai_invocations")
    op.drop_table("ai_invocations")

    op.drop_index("ix_ai_usage_budgets_workspace_id", table_name="ai_usage_budgets")
    op.drop_table("ai_usage_budgets")

    op.drop_index(
        "uq_ai_prompt_versions_active_name",
        table_name="ai_prompt_versions",
    )
    op.drop_index("ix_ai_prompt_versions_lookup", table_name="ai_prompt_versions")
    op.drop_index("ix_ai_prompt_versions_is_active", table_name="ai_prompt_versions")
    op.drop_index(
        "ix_ai_prompt_versions_created_by_user_id",
        table_name="ai_prompt_versions",
    )
    op.drop_index(
        "ix_ai_prompt_versions_workspace_id",
        table_name="ai_prompt_versions",
    )
    op.drop_table("ai_prompt_versions")

    op.drop_index(
        "ix_ai_provider_configurations_selection",
        table_name="ai_provider_configurations",
    )
    op.drop_index(
        "ix_ai_provider_configurations_is_enabled",
        table_name="ai_provider_configurations",
    )
    op.drop_index(
        "ix_ai_provider_configurations_capability_tier",
        table_name="ai_provider_configurations",
    )
    op.drop_index(
        "ix_ai_provider_configurations_provider_kind",
        table_name="ai_provider_configurations",
    )
    op.drop_index(
        "ix_ai_provider_configurations_created_by_user_id",
        table_name="ai_provider_configurations",
    )
    op.drop_index(
        "ix_ai_provider_configurations_workspace_id",
        table_name="ai_provider_configurations",
    )
    op.drop_table("ai_provider_configurations")
