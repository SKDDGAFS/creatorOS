from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utc_now
from app.models.growth_signal import SIGNAL_VALUES

if TYPE_CHECKING:
    from app.models.growth_signal import GrowthSignalProfile
    from app.models.research import ResearchFinding
    from app.models.user import User
    from app.models.workspace import Workspace


class RecommendationStatus(str, Enum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    DISMISSED = "dismissed"


class RecommendationLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class OutcomeConclusion(str, Enum):
    SUPPORTED = "supported"
    INCONCLUSIVE = "inconclusive"
    NOT_SUPPORTED = "not_supported"


class Recommendation(Base):
    __tablename__ = "recommendations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('proposed', 'accepted', 'in_progress', "
            "'completed', 'dismissed')",
            name="status_allowed",
        ),
        CheckConstraint(
            "expected_impact IN ('low', 'medium', 'high')",
            name="expected_impact_allowed",
        ),
        CheckConstraint(
            "effort_estimate IN ('low', 'medium', 'high')",
            name="effort_estimate_allowed",
        ),
        CheckConstraint(
            "risk_level IN ('low', 'medium', 'high')",
            name="risk_level_allowed",
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
        CheckConstraint("sample_size >= 1", name="sample_size_positive"),
        UniqueConstraint(
            "workspace_id",
            "fingerprint",
            name="uq_recommendations_workspace_fingerprint",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"), index=True
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    growth_signal_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "growth_signal_profiles.id",
            name="fk_recommendations_signal_profile",
            ondelete="RESTRICT",
        ),
        index=True,
    )
    proposed_action: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text)
    expected_effect: Mapped[str] = mapped_column(Text)
    uncertainty: Mapped[str] = mapped_column(Text)
    linked_goal: Mapped[str] = mapped_column(String(255), index=True)
    expected_impact: Mapped[str] = mapped_column(String(20))
    effort_estimate: Mapped[str] = mapped_column(String(20))
    risk_level: Mapped[str] = mapped_column(String(20))
    confidence: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    sample_size: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(
        String(30),
        default=RecommendationStatus.PROPOSED.value,
        server_default=RecommendationStatus.PROPOSED.value,
        index=True,
    )
    fingerprint: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        onupdate=utc_now,
    )

    workspace: Mapped[Workspace] = relationship(back_populates="recommendations")
    created_by: Mapped[User] = relationship(back_populates="recommendations_created")
    growth_signal_profile: Mapped[GrowthSignalProfile] = relationship()
    evidence: Mapped[list[RecommendationEvidence]] = relationship(
        back_populates="recommendation",
        cascade="save-update, merge",
        passive_deletes=True,
    )
    results: Mapped[list[RecommendationResult]] = relationship(
        back_populates="recommendation",
        cascade="save-update, merge",
        passive_deletes=True,
    )
    outcome_evaluation: Mapped[RecommendationOutcomeEvaluation | None] = relationship(
        back_populates="recommendation", uselist=False
    )


class RecommendationEvidence(Base):
    __tablename__ = "recommendation_evidence"
    __table_args__ = (
        CheckConstraint(f"signal IN ({SIGNAL_VALUES})", name="signal_allowed"),
        CheckConstraint(
            "normalized_value >= 0 AND normalized_value <= 1", name="value_range"
        ),
        CheckConstraint(
            "source_confidence >= 0 AND source_confidence <= 1",
            name="source_confidence_range",
        ),
        CheckConstraint("sample_size >= 1", name="sample_size_positive"),
        UniqueConstraint(
            "recommendation_id",
            "signal",
            name="uq_recommendation_evidence_recommendation_signal",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    recommendation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recommendations.id", ondelete="RESTRICT"), index=True
    )
    research_finding_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "research_findings.id",
            name="fk_recommendation_evidence_research_finding",
            ondelete="RESTRICT",
        ),
        nullable=True,
        index=True,
    )
    signal: Mapped[str] = mapped_column(String(60))
    metric_name: Mapped[str] = mapped_column(String(255))
    normalized_value: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    sample_size: Mapped[int] = mapped_column(Integer)
    source_confidence: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    explanation: Mapped[str] = mapped_column(String(2000))

    recommendation: Mapped[Recommendation] = relationship(back_populates="evidence")
    research_finding: Mapped[ResearchFinding | None] = relationship()


class RecommendationResult(Base):
    __tablename__ = "recommendation_results"
    __table_args__ = (
        CheckConstraint("sample_size >= 1", name="sample_size_positive"),
        CheckConstraint(
            "measurement_ended_at > measurement_started_at",
            name="measurement_window_order",
        ),
        UniqueConstraint(
            "recommendation_id",
            "metric_name",
            "measurement_ended_at",
            name="uq_recommendation_results_metric_window",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    recommendation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recommendations.id", ondelete="RESTRICT"), index=True
    )
    recorded_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    metric_name: Mapped[str] = mapped_column(String(255))
    baseline_value: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    observed_value: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    sample_size: Mapped[int] = mapped_column(Integer)
    measurement_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    measurement_ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )

    recommendation: Mapped[Recommendation] = relationship(back_populates="results")
    recorded_by: Mapped[User] = relationship()


class RecommendationOutcomeEvaluation(Base):
    __tablename__ = "recommendation_outcome_evaluations"
    __table_args__ = (
        CheckConstraint(
            "conclusion IN ('supported', 'inconclusive', 'not_supported')",
            name="conclusion_allowed",
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
        CheckConstraint("result_count >= 1", name="result_count_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    recommendation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "recommendations.id",
            name="fk_recommendation_evaluations_recommendation",
            ondelete="RESTRICT",
        ),
        unique=True,
        index=True,
    )
    conclusion: Mapped[str] = mapped_column(String(30))
    average_relative_change: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 6), nullable=True
    )
    confidence: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    result_count: Mapped[int] = mapped_column(Integer)
    interpretation: Mapped[str] = mapped_column(String(1000))
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )

    recommendation: Mapped[Recommendation] = relationship(
        back_populates="outcome_evaluation"
    )
