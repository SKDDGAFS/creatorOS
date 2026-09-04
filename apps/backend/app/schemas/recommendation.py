from datetime import datetime
from decimal import Decimal
from typing import Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.models.growth_signal import GrowthSignal
from app.models.recommendation import (
    OutcomeConclusion,
    RecommendationLevel,
    RecommendationStatus,
)


class RecommendationSchema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True, extra="forbid", str_strip_whitespace=True
    )


class RecommendationEvidenceCreate(RecommendationSchema):
    signal: GrowthSignal
    metric_name: str = Field(min_length=1, max_length=255)
    normalized_value: Decimal = Field(ge=0, le=1, max_digits=9, decimal_places=6)
    sample_size: int = Field(ge=1, le=1_000_000_000)
    source_confidence: Decimal = Field(ge=0, le=1, max_digits=9, decimal_places=6)
    explanation: str = Field(min_length=1, max_length=2_000)
    research_finding_id: UUID | None = None


class RecommendationCreate(RecommendationSchema):
    growth_signal_profile_id: UUID
    proposed_action: str = Field(min_length=1, max_length=5_000)
    rationale: str = Field(min_length=1, max_length=5_000)
    expected_effect: str = Field(min_length=1, max_length=2_000)
    uncertainty: str = Field(min_length=1, max_length=2_000)
    linked_goal: str = Field(min_length=1, max_length=255)
    expected_impact: RecommendationLevel
    effort_estimate: RecommendationLevel
    risk_level: RecommendationLevel
    evidence: tuple[RecommendationEvidenceCreate, ...] = Field(
        min_length=1, max_length=30
    )

    @model_validator(mode="after")
    def unique_signals(self) -> Self:
        signals = [item.signal for item in self.evidence]
        if len(set(signals)) != len(signals):
            raise ValueError("Recommendation evidence signals must be unique")
        claims = f"{self.rationale} {self.expected_effect}".casefold()
        causal_claims = ("will cause", "guarantees", "proves that", "definitely causes")
        if any(value in claims for value in causal_claims):
            raise ValueError("Recommendations must not claim causal certainty")
        return self


class RecommendationEvidenceResponse(RecommendationEvidenceCreate):
    id: UUID
    recommendation_id: UUID


class RecommendationResultCreate(RecommendationSchema):
    metric_name: str = Field(min_length=1, max_length=255)
    baseline_value: Decimal = Field(max_digits=18, decimal_places=6)
    observed_value: Decimal = Field(max_digits=18, decimal_places=6)
    sample_size: int = Field(ge=1, le=1_000_000_000)
    measurement_started_at: AwareDatetime
    measurement_ended_at: AwareDatetime
    notes: str | None = Field(default=None, min_length=1, max_length=2_000)

    @model_validator(mode="after")
    def valid_window(self) -> Self:
        if self.measurement_ended_at <= self.measurement_started_at:
            raise ValueError("Measurement end must follow its start")
        return self


class RecommendationResultResponse(RecommendationResultCreate):
    id: UUID
    recommendation_id: UUID
    recorded_by_user_id: UUID
    created_at: datetime


class OutcomeEvaluationResponse(RecommendationSchema):
    id: UUID
    recommendation_id: UUID
    conclusion: OutcomeConclusion
    average_relative_change: Decimal | None
    confidence: Decimal
    result_count: int
    interpretation: str
    evaluated_at: datetime


class RecommendationStatusUpdate(RecommendationSchema):
    status: RecommendationStatus


class RecommendationResponse(RecommendationSchema):
    id: UUID
    workspace_id: UUID
    created_by_user_id: UUID
    growth_signal_profile_id: UUID
    proposed_action: str
    rationale: str
    expected_effect: str
    uncertainty: str
    linked_goal: str
    expected_impact: RecommendationLevel
    effort_estimate: RecommendationLevel
    risk_level: RecommendationLevel
    confidence: Decimal
    sample_size: int
    status: RecommendationStatus
    evidence: list[RecommendationEvidenceResponse]
    results: list[RecommendationResultResponse]
    outcome_evaluation: OutcomeEvaluationResponse | None
    evidence_statement: str = "Correlational evidence; not proof of causation."
    created_at: datetime
    updated_at: datetime
