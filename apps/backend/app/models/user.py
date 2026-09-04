import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utc_now

if TYPE_CHECKING:
    from app.models.agent_run import AgentRun
    from app.models.ai import AIInvocation, AIPromptVersion, AIProviderConfiguration
    from app.models.auth_session import AuthSession
    from app.models.channel import Channel
    from app.models.durable_job import DurableJob
    from app.models.growth_signal import GrowthSignalProfile
    from app.models.password_reset_token import PasswordResetToken
    from app.models.platform_integration import PlatformConnection
    from app.models.publishing import PublishingJob
    from app.models.recommendation import Recommendation
    from app.models.research import Competitor, ResearchRun, ResearchSource
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
    durable_jobs_created: Mapped[list[DurableJob]] = relationship(
        back_populates="created_by",
        cascade="save-update, merge",
        passive_deletes=True,
    )
    platform_connections_created: Mapped[list[PlatformConnection]] = relationship(
        back_populates="created_by",
        cascade="save-update, merge",
        passive_deletes=True,
    )
    ai_providers_created: Mapped[list[AIProviderConfiguration]] = relationship(
        back_populates="created_by",
        cascade="save-update, merge",
        passive_deletes=True,
    )
    ai_prompt_versions_created: Mapped[list[AIPromptVersion]] = relationship(
        back_populates="created_by",
        cascade="save-update, merge",
        passive_deletes=True,
    )
    ai_invocations: Mapped[list[AIInvocation]] = relationship(
        back_populates="requested_by",
        cascade="save-update, merge",
        passive_deletes=True,
    )
    agent_runs_requested: Mapped[list[AgentRun]] = relationship(
        back_populates="requested_by",
        cascade="save-update, merge",
        passive_deletes=True,
    )
    research_sources_created: Mapped[list[ResearchSource]] = relationship(
        back_populates="created_by", cascade="save-update, merge", passive_deletes=True
    )
    competitors_created: Mapped[list[Competitor]] = relationship(
        back_populates="created_by", cascade="save-update, merge", passive_deletes=True
    )
    research_runs_requested: Mapped[list[ResearchRun]] = relationship(
        back_populates="requested_by",
        cascade="save-update, merge",
        passive_deletes=True,
    )
    recommendations_created: Mapped[list[Recommendation]] = relationship(
        back_populates="created_by", cascade="save-update, merge", passive_deletes=True
    )
