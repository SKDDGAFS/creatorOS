from datetime import datetime
from decimal import Decimal
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.channel import Platform
from app.models.growth_signal import GrowthSignal, SignalTier


class GrowthSchema(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, from_attributes=True)


class GrowthSignalWeightCreate(GrowthSchema):
    signal: GrowthSignal
    tier: SignalTier
    weight: Decimal = Field(gt=0, le=100, max_digits=9, decimal_places=6)
    minimum_sample_size: int = Field(default=1, ge=1)
    full_confidence_sample_size: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_sample_range(self) -> Self:
        if self.full_confidence_sample_size < self.minimum_sample_size:
            raise ValueError(
                "full_confidence_sample_size must be at least "
                "minimum_sample_size"
            )
        return self


class GrowthSignalWeightResponse(GrowthSignalWeightCreate):
    id: UUID


class GrowthSignalProfileCreate(GrowthSchema):
    name: str = Field(min_length=1, max_length=255)
    platform: Platform | None = None
    content_format: str | None = Field(default=None, max_length=50)
    account_size_min: int | None = Field(default=None, ge=0)
    account_size_max: int | None = Field(default=None, ge=0)
    video_duration_min_seconds: int | None = Field(default=None, gt=0)
    video_duration_max_seconds: int | None = Field(default=None, gt=0)
    goal: str | None = Field(default=None, max_length=100)
    evidence_min: int = Field(default=0, ge=0)
    evidence_max: int | None = Field(default=None, ge=0)
    weights: list[GrowthSignalWeightCreate] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def validate_context_and_weights(self) -> Self:
        ranges = (
            ("account size", self.account_size_min, self.account_size_max),
            (
                "video duration",
                self.video_duration_min_seconds,
                self.video_duration_max_seconds,
            ),
            ("evidence", self.evidence_min, self.evidence_max),
        )
        for label, minimum, maximum in ranges:
            if minimum is not None and maximum is not None and minimum > maximum:
                raise ValueError(f"{label} minimum must not exceed maximum")
        signals = [weight.signal for weight in self.weights]
        if len(signals) != len(set(signals)):
            raise ValueError("each signal may appear only once per profile")
        return self


class GrowthSignalProfileResponse(GrowthSchema):
    id: UUID
    workspace_id: UUID
    created_by_user_id: UUID
    name: str
    version: int
    platform: Platform | None
    content_format: str | None
    account_size_min: int | None
    account_size_max: int | None
    video_duration_min_seconds: int | None
    video_duration_max_seconds: int | None
    goal: str | None
    evidence_min: int
    evidence_max: int | None
    is_active: bool
    created_at: datetime
    weights: list[GrowthSignalWeightResponse]


class GrowthSignalObservation(GrowthSchema):
    signal: GrowthSignal
    value: Decimal = Field(ge=0, le=1, max_digits=9, decimal_places=6)
    sample_size: int = Field(ge=0)
    source_confidence: Decimal = Field(
        default=Decimal("1"),
        ge=0,
        le=1,
        max_digits=7,
        decimal_places=6,
    )


class GrowthScoreRequest(GrowthSchema):
    evidence_volume: int = Field(ge=0)
    observations: list[GrowthSignalObservation] = Field(
        min_length=1,
        max_length=50,
    )

    @model_validator(mode="after")
    def reject_duplicate_signals(self) -> Self:
        signals = [observation.signal for observation in self.observations]
        if len(signals) != len(set(signals)):
            raise ValueError("each signal may appear only once")
        return self


class GrowthSignalContribution(GrowthSchema):
    signal: GrowthSignal
    tier: SignalTier
    configured_weight: Decimal
    normalized_value: Decimal
    sample_confidence: Decimal
    source_confidence: Decimal
    effective_confidence: Decimal
    weighted_contribution: Decimal


class GrowthScoreResponse(GrowthSchema):
    profile_id: UUID
    profile_version: int
    score: Decimal
    confidence: Decimal
    coverage: Decimal
    contributions: list[GrowthSignalContribution]
    interpretation: str


class GrowthSignalCatalogItem(GrowthSchema):
    signal: GrowthSignal
    suggested_tier: SignalTier
