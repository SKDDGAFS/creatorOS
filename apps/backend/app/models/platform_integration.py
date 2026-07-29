from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utc_now

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.workspace import Workspace


class ConnectionStatus(str, Enum):
    CONNECTED = "connected"
    EXPIRED = "expired"
    RECONNECT_REQUIRED = "reconnect_required"
    DISCONNECTED = "disconnected"


class PlatformOperationStatus(str, Enum):
    IN_PROGRESS = "in_progress"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class RequestOutcome(str, Enum):
    SUCCEEDED = "succeeded"
    RATE_LIMITED = "rate_limited"
    TRANSIENT_FAILURE = "transient_failure"
    PERMANENT_FAILURE = "permanent_failure"
    AUTH_FAILURE = "auth_failure"


class PlatformConnection(Base):
    __tablename__ = "platform_connections"
    __table_args__ = (
        CheckConstraint(
            "platform IN ('youtube', 'tiktok', 'instagram')",
            name="platform_allowed",
        ),
        CheckConstraint(
            "status IN ('connected', 'expired', 'reconnect_required', "
            "'disconnected')",
            name="status_allowed",
        ),
        UniqueConstraint(
            "workspace_id",
            "platform",
            "external_account_id",
            name="uq_platform_connections_workspace_platform_account",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        index=True,
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
    )
    platform: Mapped[str] = mapped_column(String(20), index=True)
    external_account_id: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    credential_reference: Mapped[str] = mapped_column(String(500))
    scopes: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        default=list,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        default=ConnectionStatus.CONNECTED.value,
        server_default=ConnectionStatus.CONNECTED.value,
        index=True,
    )
    token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    connected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
    )
    last_refreshed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    disconnected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        onupdate=utc_now,
    )

    workspace: Mapped[Workspace] = relationship(
        back_populates="platform_connections"
    )
    created_by: Mapped[User] = relationship(
        back_populates="platform_connections_created"
    )
    sync_cursors: Mapped[list[PlatformSyncCursor]] = relationship(
        back_populates="connection",
        cascade="save-update, merge",
        passive_deletes=True,
    )
    operations: Mapped[list[PlatformOperation]] = relationship(
        back_populates="connection",
        cascade="save-update, merge",
        passive_deletes=True,
    )
    request_logs: Mapped[list[PlatformRequestLog]] = relationship(
        back_populates="connection",
        cascade="save-update, merge",
        passive_deletes=True,
    )


class PlatformSyncCursor(Base):
    __tablename__ = "platform_sync_cursors"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "resource_type",
            name="uq_platform_sync_cursors_connection_resource",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    connection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("platform_connections.id", ondelete="RESTRICT"),
        index=True,
    )
    resource_type: Mapped[str] = mapped_column(String(100))
    cursor: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        onupdate=utc_now,
    )

    connection: Mapped[PlatformConnection] = relationship(
        back_populates="sync_cursors"
    )


class PlatformOperation(Base):
    __tablename__ = "platform_operations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('in_progress', 'succeeded', 'failed')",
            name="status_allowed",
        ),
        UniqueConstraint(
            "connection_id",
            "operation_type",
            "idempotency_key_hash",
            name="uq_platform_operations_connection_type_idempotency",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    connection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("platform_connections.id", ondelete="RESTRICT"),
        index=True,
    )
    operation_type: Mapped[str] = mapped_column(String(100), index=True)
    idempotency_key_hash: Mapped[str] = mapped_column(String(64))
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(
        String(20),
        default=PlatformOperationStatus.IN_PROGRESS.value,
        server_default=PlatformOperationStatus.IN_PROGRESS.value,
        index=True,
    )
    external_resource_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    last_error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    connection: Mapped[PlatformConnection] = relationship(
        back_populates="operations"
    )
    request_logs: Mapped[list[PlatformRequestLog]] = relationship(
        back_populates="operation",
        cascade="save-update, merge",
        passive_deletes=True,
    )


class PlatformRequestLog(Base):
    __tablename__ = "platform_request_logs"
    __table_args__ = (
        CheckConstraint(
            "outcome IN ('succeeded', 'rate_limited', 'transient_failure', "
            "'permanent_failure', 'auth_failure')",
            name="outcome_allowed",
        ),
        CheckConstraint(
            "duration_ms >= 0",
            name="duration_ms_nonnegative",
        ),
        CheckConstraint(
            "status_code IS NULL OR "
            "(status_code >= 100 AND status_code <= 599)",
            name="status_code_range",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    connection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("platform_connections.id", ondelete="RESTRICT"),
        index=True,
    )
    operation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("platform_operations.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    method: Mapped[str] = mapped_column(String(10))
    host: Mapped[str] = mapped_column(String(255))
    path: Mapped[str] = mapped_column(String(1000))
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer)
    outcome: Mapped[str] = mapped_column(String(30), index=True)
    provider_request_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    request_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
    )

    connection: Mapped[PlatformConnection] = relationship(
        back_populates="request_logs"
    )
    operation: Mapped[PlatformOperation | None] = relationship(
        back_populates="request_logs"
    )


class OAuthAuthorizationState(Base):
    __tablename__ = "oauth_authorization_states"
    __table_args__ = (
        CheckConstraint(
            "platform IN ('youtube', 'tiktok', 'instagram')",
            name="platform_allowed",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        index=True,
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
    )
    platform: Mapped[str] = mapped_column(String(20), index=True)
    state_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    secret_reference: Mapped[str] = mapped_column(String(500))
    requested_scopes: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
    )
    redirect_uri: Mapped[str] = mapped_column(String(2000))
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
    )
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
    )


class PlatformQuotaUsage(Base):
    __tablename__ = "platform_quota_usage"
    __table_args__ = (
        CheckConstraint("units >= 0", name="units_nonnegative"),
        CheckConstraint(
            "request_count >= 0",
            name="request_count_nonnegative",
        ),
        UniqueConstraint(
            "connection_id",
            "usage_date",
            "quota_bucket",
            name="uq_platform_quota_usage_connection_date_bucket",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    connection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("platform_connections.id", ondelete="RESTRICT"),
        index=True,
    )
    usage_date: Mapped[date] = mapped_column(Date)
    quota_bucket: Mapped[str] = mapped_column(String(100))
    units: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    request_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        onupdate=utc_now,
    )
