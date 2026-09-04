import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Self
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.models.channel import Platform
from app.models.research import (
    FreshnessStatus,
    ResearchFindingType,
    ResearchRunStatus,
    ResearchSourceType,
)


class ResearchSchema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        str_strip_whitespace=True,
    )


def _https_url(value: str | None) -> str | None:
    if value is None:
        return None
    if not value.lower().startswith("https://"):
        raise ValueError("Research links must use HTTPS")
    if len(value) > 2048:
        raise ValueError("Research link is too long")
    return value


class ResearchSourceCreate(ResearchSchema):
    source_type: ResearchSourceType
    title: str = Field(min_length=1, max_length=500)
    canonical_url: str | None = Field(default=None, max_length=2048)
    publisher: str | None = Field(default=None, min_length=1, max_length=255)
    excerpt: str = Field(min_length=1, max_length=5_000)
    source_date: AwareDatetime
    stale_after_days: int = Field(default=30, ge=1, le=3650)
    source_metadata: dict[str, str | int | float | bool | None] = Field(
        default_factory=dict,
        max_length=50,
    )

    _validate_url = field_validator("canonical_url")(_https_url)

    @field_validator("source_date")
    @classmethod
    def reject_future_source_date(cls, value: datetime) -> datetime:
        if value.astimezone(UTC) > datetime.now(UTC) + timedelta(minutes=5):
            raise ValueError("Research source date cannot be in the future")
        return value

    @model_validator(mode="after")
    def require_public_evidence_url(self) -> Self:
        if (
            self.source_type
            in {ResearchSourceType.OFFICIAL_API, ResearchSourceType.PUBLIC_WEB}
            and self.canonical_url is None
        ):
            raise ValueError("Official API and public web sources require an HTTPS URL")
        if any(len(key) > 100 for key in self.source_metadata):
            raise ValueError("Research metadata keys are too long")
        if len(json.dumps(self.source_metadata, separators=(",", ":"))) > 10_000:
            raise ValueError("Research metadata is too large")
        return self


class ResearchSourceResponse(ResearchSchema):
    id: UUID
    workspace_id: UUID
    created_by_user_id: UUID
    source_type: ResearchSourceType
    title: str
    canonical_url: str | None
    publisher: str | None
    excerpt: str
    source_date: datetime
    retrieved_at: datetime
    stale_after_days: int
    freshness_status: FreshnessStatus
    source_metadata: dict[str, object]
    created_at: datetime


class CompetitorCreate(ResearchSchema):
    name: str = Field(min_length=1, max_length=255)
    platform: Platform
    handle: str = Field(min_length=1, max_length=255, pattern=r"^@?[A-Za-z0-9._-]+$")
    profile_url: str | None = Field(default=None, max_length=2048)
    notes: str | None = Field(default=None, min_length=1, max_length=5_000)

    _validate_url = field_validator("profile_url")(_https_url)


class CompetitorResponse(CompetitorCreate):
    id: UUID
    workspace_id: UUID
    created_by_user_id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ResearchRunCreate(ResearchSchema):
    objective: str = Field(min_length=1, max_length=5_000)
    source_ids: tuple[UUID, ...] = Field(min_length=1, max_length=10)
    competitor_ids: tuple[UUID, ...] = Field(default=(), max_length=20)
    include_stale_sources: bool = False
    priority: int = Field(default=50, ge=0, le=100)
    max_attempts: int = Field(default=3, ge=1, le=10)

    @model_validator(mode="after")
    def require_unique_references(self) -> Self:
        if len(set(self.source_ids)) != len(self.source_ids):
            raise ValueError("Research source IDs must be unique")
        if len(set(self.competitor_ids)) != len(self.competitor_ids):
            raise ValueError("Competitor IDs must be unique")
        return self


class ResearchRunResponse(ResearchSchema):
    id: UUID
    workspace_id: UUID
    requested_by_user_id: UUID
    prompt_version_id: UUID
    durable_job_id: UUID
    ai_invocation_id: UUID | None
    objective: str
    source_ids: list[str]
    competitor_ids: list[str]
    include_stale_sources: bool
    status: ResearchRunStatus
    model_name: str | None
    estimated_cost_usd: Decimal
    summary: str | None
    fresh_source_count: int
    stale_source_count: int
    last_error_code: str | None
    last_error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class EvidenceDraft(ResearchSchema):
    source_id: UUID
    evidence_note: str = Field(min_length=1, max_length=1_000)


class ResearchFindingDraft(ResearchSchema):
    finding_type: ResearchFindingType
    title: str = Field(min_length=1, max_length=500)
    summary: str = Field(min_length=1, max_length=5_000)
    confidence: Decimal = Field(ge=0, le=1, max_digits=5, decimal_places=4)
    evidence: tuple[EvidenceDraft, ...] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def unique_evidence_sources(self) -> Self:
        ids = [item.source_id for item in self.evidence]
        if len(set(ids)) != len(ids):
            raise ValueError("Finding evidence source IDs must be unique")
        return self


class ResearchHookDraft(ResearchSchema):
    text: str = Field(min_length=1, max_length=1_000)
    rationale: str = Field(min_length=1, max_length=2_000)
    confidence: Decimal = Field(ge=0, le=1, max_digits=5, decimal_places=4)
    source_ids: tuple[UUID, ...] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def unique_sources(self) -> Self:
        if len(set(self.source_ids)) != len(self.source_ids):
            raise ValueError("Hook source IDs must be unique")
        return self


class ContentIdeaDraft(ResearchSchema):
    title: str = Field(min_length=1, max_length=500)
    concept: str = Field(min_length=1, max_length=5_000)
    suggested_hook: str | None = Field(default=None, min_length=1, max_length=1_000)
    platforms: tuple[Platform, ...] = Field(min_length=1, max_length=3)
    source_ids: tuple[UUID, ...] = Field(min_length=1, max_length=10)
    confidence: Decimal = Field(ge=0, le=1, max_digits=5, decimal_places=4)

    @model_validator(mode="after")
    def unique_references(self) -> Self:
        if len(set(self.source_ids)) != len(self.source_ids):
            raise ValueError("Content idea source IDs must be unique")
        if len(set(self.platforms)) != len(self.platforms):
            raise ValueError("Content idea platforms must be unique")
        return self


class ResearchOutput(ResearchSchema):
    summary: str = Field(min_length=1, max_length=5_000)
    findings: tuple[ResearchFindingDraft, ...] = Field(default=(), max_length=30)
    hooks: tuple[ResearchHookDraft, ...] = Field(default=(), max_length=30)
    content_ideas: tuple[ContentIdeaDraft, ...] = Field(default=(), max_length=30)


class FindingEvidenceResponse(ResearchSchema):
    source_id: UUID
    evidence_note: str


class ResearchFindingResponse(ResearchSchema):
    id: UUID
    workspace_id: UUID
    first_seen_run_id: UUID
    last_seen_run_id: UUID
    finding_type: ResearchFindingType
    title: str
    summary: str
    confidence: Decimal
    source_date: datetime
    freshness_status: FreshnessStatus
    evidence: list[FindingEvidenceResponse]
    first_seen_at: datetime
    last_seen_at: datetime


class ResearchHookResponse(ResearchSchema):
    id: UUID
    workspace_id: UUID
    first_seen_run_id: UUID
    last_seen_run_id: UUID
    text: str
    rationale: str
    confidence: Decimal
    source_ids: list[str]
    first_seen_at: datetime
    last_seen_at: datetime


class ContentIdeaResponse(ResearchSchema):
    id: UUID
    workspace_id: UUID
    first_seen_run_id: UUID
    last_seen_run_id: UUID
    title: str
    concept: str
    suggested_hook: str | None
    platforms: list[str]
    source_ids: list[str]
    confidence: Decimal
    first_seen_at: datetime
    last_seen_at: datetime
