import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utc_now

if TYPE_CHECKING:
    from app.models.channel import Channel
    from app.models.growth_signal import GrowthSignalProfile
    from app.models.publishing import ActivityEvent, PublishingJob
    from app.models.user import User


class WorkspaceRole(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
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

    memberships: Mapped[list[WorkspaceMembership]] = relationship(
        back_populates="workspace",
        cascade="save-update, merge",
        passive_deletes=True,
    )
    channels: Mapped[list[Channel]] = relationship(
        back_populates="workspace",
        cascade="save-update, merge",
        passive_deletes=True,
    )
    growth_signal_profiles: Mapped[list[GrowthSignalProfile]] = relationship(
        back_populates="workspace",
        cascade="save-update, merge",
        passive_deletes=True,
    )
    publishing_jobs: Mapped[list[PublishingJob]] = relationship(
        back_populates="workspace",
        cascade="save-update, merge",
        passive_deletes=True,
    )
    activity_events: Mapped[list[ActivityEvent]] = relationship(
        back_populates="workspace",
        cascade="save-update, merge",
        passive_deletes=True,
    )


class WorkspaceMembership(Base):
    __tablename__ = "workspace_memberships"
    __table_args__ = (
        CheckConstraint(
            "role IN ('owner', 'admin', 'member', 'viewer')",
            name="role_allowed",
        ),
        UniqueConstraint(
            "workspace_id",
            "user_id",
            name="uq_workspace_memberships_workspace_id_user_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
    )
    role: Mapped[str] = mapped_column(
        String(20),
        default=WorkspaceRole.MEMBER.value,
        server_default=WorkspaceRole.MEMBER.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
    )

    workspace: Mapped[Workspace] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="workspace_memberships")
