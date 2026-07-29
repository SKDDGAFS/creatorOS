"""Add platform connection, cursor, operation, and request-log records.

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-29
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "platform_connections",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("platform", sa.String(20), nullable=False),
        sa.Column("external_account_id", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("credential_reference", sa.String(500), nullable=False),
        sa.Column(
            "scopes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(30),
            server_default=sa.text("'connected'"),
            nullable=False,
        ),
        sa.Column(
            "token_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "connected_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_refreshed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "disconnected_at",
            sa.DateTime(timezone=True),
            nullable=True,
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
            name=op.f("ck_platform_connections_platform_allowed"),
        ),
        sa.CheckConstraint(
            "status IN ('connected', 'expired', 'reconnect_required', "
            "'disconnected')",
            name=op.f("ck_platform_connections_status_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_platform_connections_workspace_id_workspaces",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_platform_connections_created_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_platform_connections"),
        sa.UniqueConstraint(
            "workspace_id",
            "platform",
            "external_account_id",
            name="uq_platform_connections_workspace_platform_account",
        ),
    )
    op.create_index(
        "ix_platform_connections_workspace_id",
        "platform_connections",
        ["workspace_id"],
    )
    op.create_index(
        "ix_platform_connections_created_by_user_id",
        "platform_connections",
        ["created_by_user_id"],
    )
    op.create_index(
        "ix_platform_connections_platform",
        "platform_connections",
        ["platform"],
    )
    op.create_index(
        "ix_platform_connections_status",
        "platform_connections",
        ["status"],
    )

    op.create_table(
        "platform_sync_cursors",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "connection_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("resource_type", sa.String(100), nullable=False),
        sa.Column("cursor", sa.Text(), nullable=True),
        sa.Column(
            "last_synced_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["connection_id"],
            ["platform_connections.id"],
            name=(
                "fk_platform_sync_cursors_connection_id_"
                "platform_connections"
            ),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_platform_sync_cursors"),
        sa.UniqueConstraint(
            "connection_id",
            "resource_type",
            name="uq_platform_sync_cursors_connection_resource",
        ),
    )
    op.create_index(
        "ix_platform_sync_cursors_connection_id",
        "platform_sync_cursors",
        ["connection_id"],
    )

    op.create_table(
        "platform_operations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "connection_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("operation_type", sa.String(100), nullable=False),
        sa.Column("idempotency_key_hash", sa.String(64), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            server_default=sa.text("'in_progress'"),
            nullable=False,
        ),
        sa.Column("external_resource_id", sa.String(255), nullable=True),
        sa.Column("last_error_code", sa.String(100), nullable=True),
        sa.Column("last_error_message", sa.String(500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.CheckConstraint(
            "status IN ('in_progress', 'succeeded', 'failed')",
            name=op.f("ck_platform_operations_status_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["connection_id"],
            ["platform_connections.id"],
            name="fk_platform_operations_connection_id_platform_connections",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_platform_operations"),
        sa.UniqueConstraint(
            "connection_id",
            "operation_type",
            "idempotency_key_hash",
            name="uq_platform_operations_connection_type_idempotency",
        ),
    )
    op.create_index(
        "ix_platform_operations_connection_id",
        "platform_operations",
        ["connection_id"],
    )
    op.create_index(
        "ix_platform_operations_operation_type",
        "platform_operations",
        ["operation_type"],
    )
    op.create_index(
        "ix_platform_operations_status",
        "platform_operations",
        ["status"],
    )

    op.create_table(
        "platform_request_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "connection_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "operation_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("host", sa.String(255), nullable=False),
        sa.Column("path", sa.String(1000), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(30), nullable=False),
        sa.Column("provider_request_id", sa.String(255), nullable=True),
        sa.Column(
            "request_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "outcome IN ('succeeded', 'rate_limited', "
            "'transient_failure', 'permanent_failure', 'auth_failure')",
            name=op.f("ck_platform_request_logs_outcome_allowed"),
        ),
        sa.CheckConstraint(
            "duration_ms >= 0",
            name=op.f("ck_platform_request_logs_duration_ms_nonnegative"),
        ),
        sa.CheckConstraint(
            "status_code IS NULL OR "
            "(status_code >= 100 AND status_code <= 599)",
            name=op.f("ck_platform_request_logs_status_code_range"),
        ),
        sa.ForeignKeyConstraint(
            ["connection_id"],
            ["platform_connections.id"],
            name=(
                "fk_platform_request_logs_connection_id_"
                "platform_connections"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["operation_id"],
            ["platform_operations.id"],
            name="fk_platform_request_logs_operation_id_platform_operations",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_platform_request_logs"),
    )
    op.create_index(
        "ix_platform_request_logs_connection_id",
        "platform_request_logs",
        ["connection_id"],
    )
    op.create_index(
        "ix_platform_request_logs_operation_id",
        "platform_request_logs",
        ["operation_id"],
    )
    op.create_index(
        "ix_platform_request_logs_outcome",
        "platform_request_logs",
        ["outcome"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_platform_request_logs_outcome",
        table_name="platform_request_logs",
    )
    op.drop_index(
        "ix_platform_request_logs_operation_id",
        table_name="platform_request_logs",
    )
    op.drop_index(
        "ix_platform_request_logs_connection_id",
        table_name="platform_request_logs",
    )
    op.drop_table("platform_request_logs")

    op.drop_index(
        "ix_platform_operations_status",
        table_name="platform_operations",
    )
    op.drop_index(
        "ix_platform_operations_operation_type",
        table_name="platform_operations",
    )
    op.drop_index(
        "ix_platform_operations_connection_id",
        table_name="platform_operations",
    )
    op.drop_table("platform_operations")

    op.drop_index(
        "ix_platform_sync_cursors_connection_id",
        table_name="platform_sync_cursors",
    )
    op.drop_table("platform_sync_cursors")

    op.drop_index(
        "ix_platform_connections_status",
        table_name="platform_connections",
    )
    op.drop_index(
        "ix_platform_connections_platform",
        table_name="platform_connections",
    )
    op.drop_index(
        "ix_platform_connections_created_by_user_id",
        table_name="platform_connections",
    )
    op.drop_index(
        "ix_platform_connections_workspace_id",
        table_name="platform_connections",
    )
    op.drop_table("platform_connections")
