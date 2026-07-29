from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.models.growth_signal import (
    GrowthSignal,
    GrowthSignalProfile,
    GrowthSignalWeight,
    SignalTier,
)
from app.schemas.growth_signal import (
    GrowthScoreRequest,
    GrowthScoreResponse,
    GrowthSignalCatalogItem,
    GrowthSignalContribution,
    GrowthSignalProfileCreate,
)
from app.services.errors import (
    ConflictError,
    InvalidRequestError,
    PersistenceError,
    ResourceNotFoundError,
)

SIX_PLACES = Decimal("0.000001")

STRONG_SIGNALS = {
    GrowthSignal.RETENTION_CURVE,
    GrowthSignal.COMPLETION_RATE,
    GrowthSignal.AVERAGE_PERCENTAGE_VIEWED,
    GrowthSignal.FIRST_HOUR_PERFORMANCE,
    GrowthSignal.SHARE_RATE,
    GrowthSignal.FOLLOWER_CONVERSION_RATE,
    GrowthSignal.RECOMMENDATION_TRAFFIC,
    GrowthSignal.NEW_VIEWER_REACH,
    GrowthSignal.IMPRESSIONS_TO_VIEW_RATE,
    GrowthSignal.RETURNING_VIEWER_TREND,
}
MEDIUM_SIGNALS = {
    GrowthSignal.SAVE_RATE,
    GrowthSignal.NORMALIZED_ENGAGEMENT_RATE,
    GrowthSignal.SEARCH_TRAFFIC,
    GrowthSignal.HASHTAG_REACH,
    GrowthSignal.SOUND_REACH,
    GrowthSignal.POSTING_TIME_PERFORMANCE,
    GrowthSignal.GEOGRAPHIC_FIT,
}


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(SIX_PLACES, rounding=ROUND_HALF_UP)


def signal_catalog() -> list[GrowthSignalCatalogItem]:
    items = []
    for signal in GrowthSignal:
        if signal in STRONG_SIGNALS:
            tier = SignalTier.STRONG
        elif signal in MEDIUM_SIGNALS:
            tier = SignalTier.MEDIUM
        else:
            tier = SignalTier.CONTEXTUAL
        items.append(
            GrowthSignalCatalogItem(
                signal=signal,
                suggested_tier=tier,
            )
        )
    return items


def create_profile(
    db: Session,
    *,
    workspace_id: UUID,
    user_id: UUID,
    payload: GrowthSignalProfileCreate,
) -> GrowthSignalProfile:
    latest_version = db.scalar(
        select(func.max(GrowthSignalProfile.version)).where(
            GrowthSignalProfile.workspace_id == workspace_id,
            GrowthSignalProfile.name == payload.name,
        )
    )
    profile_values = payload.model_dump(exclude={"weights", "platform"})
    profile = GrowthSignalProfile(
        **profile_values,
        workspace_id=workspace_id,
        created_by_user_id=user_id,
        version=(latest_version or 0) + 1,
        platform=payload.platform.value if payload.platform else None,
        weights=[
            GrowthSignalWeight(
                **weight.model_dump(exclude={"signal", "tier"}),
                signal=weight.signal.value,
                tier=weight.tier.value,
            )
            for weight in payload.weights
        ],
    )
    db.add(profile)
    try:
        db.commit()
        db.refresh(profile)
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("Unable to allocate a unique profile version") from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise PersistenceError("Unable to create growth-signal profile") from exc
    return profile


def list_profiles(
    db: Session,
    *,
    workspace_id: UUID,
    include_inactive: bool,
) -> list[GrowthSignalProfile]:
    statement = (
        select(GrowthSignalProfile)
        .options(selectinload(GrowthSignalProfile.weights))
        .where(GrowthSignalProfile.workspace_id == workspace_id)
    )
    if not include_inactive:
        statement = statement.where(GrowthSignalProfile.is_active.is_(True))
    statement = statement.order_by(
        GrowthSignalProfile.name,
        GrowthSignalProfile.version.desc(),
        GrowthSignalProfile.id,
    )
    return list(db.scalars(statement).all())


def get_profile(
    db: Session,
    *,
    workspace_id: UUID,
    profile_id: UUID,
) -> GrowthSignalProfile:
    profile = db.scalar(
        select(GrowthSignalProfile)
        .options(selectinload(GrowthSignalProfile.weights))
        .where(
            GrowthSignalProfile.id == profile_id,
            GrowthSignalProfile.workspace_id == workspace_id,
        )
    )
    if profile is None:
        raise ResourceNotFoundError("Growth-signal profile not found")
    return profile


def deactivate_profile(
    db: Session,
    *,
    workspace_id: UUID,
    profile_id: UUID,
) -> GrowthSignalProfile:
    profile = get_profile(
        db,
        workspace_id=workspace_id,
        profile_id=profile_id,
    )
    profile.is_active = False
    try:
        db.commit()
        db.refresh(profile)
    except SQLAlchemyError as exc:
        db.rollback()
        raise PersistenceError("Unable to deactivate growth-signal profile") from exc
    return profile


def score_profile(
    db: Session,
    *,
    workspace_id: UUID,
    profile_id: UUID,
    payload: GrowthScoreRequest,
) -> GrowthScoreResponse:
    profile = get_profile(
        db,
        workspace_id=workspace_id,
        profile_id=profile_id,
    )
    if not profile.is_active:
        raise InvalidRequestError("Inactive profiles cannot score new observations")
    if payload.evidence_volume < profile.evidence_min or (
        profile.evidence_max is not None
        and payload.evidence_volume > profile.evidence_max
    ):
        raise InvalidRequestError(
            "Evidence volume is outside this profile's configured range"
        )

    observations = {
        observation.signal.value: observation
        for observation in payload.observations
    }
    total_weight = sum(
        (weight.weight for weight in profile.weights),
        start=Decimal("0"),
    )
    if total_weight <= 0:
        raise InvalidRequestError("Profile has no usable configured weights")
    observed_weight = Decimal("0")
    weighted_score = Decimal("0")
    weighted_confidence = Decimal("0")
    contributions: list[GrowthSignalContribution] = []

    for weight in profile.weights:
        observation = observations.get(weight.signal)
        if observation is None:
            continue
        observed_weight += weight.weight
        if observation.sample_size < weight.minimum_sample_size:
            sample_confidence = Decimal("0")
        else:
            sample_confidence = min(
                Decimal("1"),
                Decimal(observation.sample_size)
                / Decimal(weight.full_confidence_sample_size),
            )
        effective_confidence = (
            sample_confidence * observation.source_confidence
        )
        contribution = (
            weight.weight * observation.value * effective_confidence
        )
        weighted_score += contribution
        weighted_confidence += weight.weight * effective_confidence
        contributions.append(
            GrowthSignalContribution(
                signal=GrowthSignal(weight.signal),
                tier=SignalTier(weight.tier),
                configured_weight=weight.weight,
                normalized_value=observation.value,
                sample_confidence=_quantize(sample_confidence),
                source_confidence=observation.source_confidence,
                effective_confidence=_quantize(effective_confidence),
                weighted_contribution=_quantize(contribution),
            )
        )

    score = _quantize(weighted_score / total_weight)
    confidence = _quantize(weighted_confidence / total_weight)
    coverage = _quantize(observed_weight / total_weight)
    if confidence < Decimal("0.3"):
        interpretation = (
            "Low-confidence association; gather more evidence before acting."
        )
    elif confidence < Decimal("0.7"):
        interpretation = (
            "Moderate-confidence association; treat the score as directional."
        )
    else:
        interpretation = (
            "Higher-confidence association; this remains correlational evidence."
        )
    return GrowthScoreResponse(
        profile_id=profile.id,
        profile_version=profile.version,
        score=score,
        confidence=confidence,
        coverage=coverage,
        contributions=contributions,
        interpretation=interpretation,
    )
