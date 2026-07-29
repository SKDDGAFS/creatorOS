import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utc_now

if TYPE_CHECKING:
    from app.models.auth_session import AuthSession
    from app.models.channel import Channel
    from app.models.growth_signal import GrowthSignalProfile
    from app.models.password_reset_token import PasswordResetToken
    from app.models.publishing import PublishingJob
    from app.models.workspace import WorkspaceMembership


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
    )
    disabled_at: Mapped[datetime | None] = mapped_column(
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

    channels: Mapped[list[Channel]] = relationship(
        back_populates="user",
        cascade="save-update, merge",
        passive_deletes=True,
    )
    workspace_memberships: Mapped[list[WorkspaceMembership]] = relationship(
        back_populates="user",
        cascade="save-update, merge",
        passive_deletes=True,
    )
    auth_sessions: Mapped[list[AuthSession]] = relationship(
        back_populates="user",
        cascade="save-update, merge",
        passive_deletes=True,
    )
    password_reset_tokens: Mapped[list[PasswordResetToken]] = relationship(
        back_populates="user",
        cascade="save-update, merge",
        passive_deletes=True,
    )
    growth_signal_profiles_created: Mapped[list[GrowthSignalProfile]] = relationship(
        back_populates="created_by",
        cascade="save-update, merge",
        passive_deletes=True,
    )
    publishing_jobs_created: Mapped[list[PublishingJob]] = relationship(
        back_populates="created_by",
        cascade="save-update, merge",
        passive_deletes=True,
    )
