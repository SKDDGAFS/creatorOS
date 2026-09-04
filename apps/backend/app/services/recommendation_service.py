import hashlib
import json
import re
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.models.recommendation import (
    OutcomeConclusion,
    Recommendation,
    RecommendationEvidence,
    RecommendationOutcomeEvaluation,
    RecommendationResult,
    RecommendationStatus,
)
from app.models.research import ResearchFinding
from app.schemas.growth_signal import GrowthScoreRequest, GrowthSignalObservation
from app.schemas.recommendation import (
    RecommendationCreate,
    RecommendationResultCreate,
)
from app.services import growth_signal_service
from app.services.errors import (
    ConflictError,
    InvalidRequestError,
    PersistenceError,
    ResourceNotFoundError,
)

SIX_PLACES = Decimal("0.000001")
LOAD_OPTIONS = (
    selectinload(Recommendation.evidence),
    selectinload(Recommendation.results),
    selectinload(Recommendation.outcome_evaluation),
)
TRANSITIONS = {
    RecommendationStatus.PROPOSED: {
        RecommendationStatus.ACCEPTED,
        RecommendationStatus.DISMISSED,
    },
    RecommendationStatus.ACCEPTED: {
        RecommendationStatus.IN_PROGRESS,
        RecommendationStatus.DISMISSED,
    },
    RecommendationStatus.IN_PROGRESS: {
        RecommendationStatus.COMPLETED,
        RecommendationStatus.DISMISSED,
    },
    RecommendationStatus.COMPLETED: set(),
    RecommendationStatus.DISMISSED: set(),
}


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(SIX_PLACES, rounding=ROUND_HALF_UP)


def _canonical(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _fingerprint(payload: RecommendationCreate) -> str:
    value = {
        "profile": str(payload.growth_signal_profile_id),
        "action": _canonical(payload.proposed_action),
        "goal": _canonical(payload.linked_goal),
        "evidence": sorted(item.signal.value for item in payload.evidence),
    }
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _commit(db: Session, conflict: str, failure: str) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(conflict) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise PersistenceError(failure) from exc


def _validate_research_findings(
    db: Session, *, workspace_id: UUID, finding_ids: set[UUID]
) -> None:
    if not finding_ids:
        return
    found = set(
        db.scalars(
            select(ResearchFinding.id).where(
                ResearchFinding.workspace_id == workspace_id,
                ResearchFinding.id.in_(finding_ids),
            )
        ).all()
    )
    if found != finding_ids:
        raise ResourceNotFoundError("Recommendation research evidence not found")


def create_recommendation(
    db: Session,
    *,
    workspace_id: UUID,
    user_id: UUID,
    payload: RecommendationCreate,
) -> tuple[Recommendation, bool]:
    finding_ids = {
        item.research_finding_id
        for item in payload.evidence
        if item.research_finding_id is not None
    }
    _validate_research_findings(db, workspace_id=workspace_id, finding_ids=finding_ids)
    sample_size = sum(item.sample_size for item in payload.evidence)
    score = growth_signal_service.score_profile(
        db,
        workspace_id=workspace_id,
        profile_id=payload.growth_signal_profile_id,
        payload=GrowthScoreRequest(
            evidence_volume=sample_size,
            observations=[
                GrowthSignalObservation(
                    signal=item.signal,
                    value=item.normalized_value,
                    sample_size=item.sample_size,
                    source_confidence=item.source_confidence,
                )
                for item in payload.evidence
            ],
        ),
    )
    fingerprint = _fingerprint(payload)
    existing = db.scalar(
        select(Recommendation)
        .options(*LOAD_OPTIONS)
        .execution_options(populate_existing=True)
        .where(
            Recommendation.workspace_id == workspace_id,
            Recommendation.fingerprint == fingerprint,
        )
    )
    if existing is not None:
        return existing, False
    recommendation = Recommendation(
        workspace_id=workspace_id,
        created_by_user_id=user_id,
        growth_signal_profile_id=payload.growth_signal_profile_id,
        proposed_action=payload.proposed_action,
        rationale=payload.rationale,
        expected_effect=payload.expected_effect,
        uncertainty=payload.uncertainty,
        linked_goal=payload.linked_goal,
        expected_impact=payload.expected_impact.value,
        effort_estimate=payload.effort_estimate.value,
        risk_level=payload.risk_level.value,
        confidence=score.confidence,
        sample_size=sample_size,
        status=RecommendationStatus.PROPOSED.value,
        fingerprint=fingerprint,
        evidence=[
            RecommendationEvidence(
                research_finding_id=item.research_finding_id,
                signal=item.signal.value,
                metric_name=item.metric_name,
                normalized_value=item.normalized_value,
                sample_size=item.sample_size,
                source_confidence=item.source_confidence,
                explanation=item.explanation,
            )
            for item in payload.evidence
        ],
    )
    db.add(recommendation)
    _commit(
        db,
        "Recommendation already exists",
        "Unable to create recommendation",
    )
    db.refresh(recommendation)
    return get_recommendation(
        db, workspace_id=workspace_id, recommendation_id=recommendation.id
    ), True


def get_recommendation(
    db: Session, *, workspace_id: UUID, recommendation_id: UUID
) -> Recommendation:
    recommendation = db.scalar(
        select(Recommendation)
        .options(*LOAD_OPTIONS)
        .execution_options(populate_existing=True)
        .where(
            Recommendation.id == recommendation_id,
            Recommendation.workspace_id == workspace_id,
        )
    )
    if recommendation is None:
        raise ResourceNotFoundError("Recommendation not found")
    return recommendation


def list_recommendations(
    db: Session,
    *,
    workspace_id: UUID,
    status: RecommendationStatus | None,
    limit: int,
    offset: int,
) -> list[Recommendation]:
    statement: Select[tuple[Recommendation]] = (
        select(Recommendation)
        .options(*LOAD_OPTIONS)
        .where(Recommendation.workspace_id == workspace_id)
    )
    if status is not None:
        statement = statement.where(Recommendation.status == status.value)
    return list(
        db.scalars(
            statement.order_by(Recommendation.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        .unique()
        .all()
    )


def transition_status(
    db: Session,
    *,
    workspace_id: UUID,
    recommendation_id: UUID,
    target: RecommendationStatus,
) -> Recommendation:
    recommendation = get_recommendation(
        db, workspace_id=workspace_id, recommendation_id=recommendation_id
    )
    current = RecommendationStatus(recommendation.status)
    if target == current:
        return recommendation
    if target not in TRANSITIONS[current]:
        raise InvalidRequestError("Recommendation status transition is not allowed")
    recommendation.status = target.value
    _commit(db, "Unable to change recommendation", "Unable to change recommendation")
    return recommendation


def add_result(
    db: Session,
    *,
    workspace_id: UUID,
    recommendation_id: UUID,
    user_id: UUID,
    payload: RecommendationResultCreate,
) -> RecommendationResult:
    recommendation = get_recommendation(
        db, workspace_id=workspace_id, recommendation_id=recommendation_id
    )
    if recommendation.status not in {
        RecommendationStatus.IN_PROGRESS.value,
        RecommendationStatus.COMPLETED.value,
    }:
        raise InvalidRequestError(
            "Results require an in-progress or completed recommendation"
        )
    result = RecommendationResult(
        recommendation_id=recommendation.id,
        recorded_by_user_id=user_id,
        **payload.model_dump(),
    )
    db.add(result)
    _commit(db, "Result already exists", "Unable to record recommendation result")
    db.refresh(result)
    return result


def evaluate_outcome(
    db: Session, *, workspace_id: UUID, recommendation_id: UUID
) -> RecommendationOutcomeEvaluation:
    recommendation = get_recommendation(
        db, workspace_id=workspace_id, recommendation_id=recommendation_id
    )
    if not recommendation.results:
        raise InvalidRequestError("At least one result is required for evaluation")
    usable = [item for item in recommendation.results if item.baseline_value != 0]
    total_sample = sum(item.sample_size for item in recommendation.results)
    average_change = None
    if usable:
        weighted_change = sum(
            (
                (item.observed_value - item.baseline_value)
                / abs(item.baseline_value)
                * item.sample_size
                for item in usable
            ),
            start=Decimal("0"),
        )
        usable_sample = sum(item.sample_size for item in usable)
        average_change = _quantize(weighted_change / Decimal(usable_sample))
    outcome_confidence = _quantize(
        recommendation.confidence
        * min(Decimal("1"), Decimal(total_sample) / Decimal("100"))
    )
    if average_change is None or outcome_confidence < Decimal("0.3"):
        conclusion = OutcomeConclusion.INCONCLUSIVE
    elif average_change > Decimal("0.05"):
        conclusion = OutcomeConclusion.SUPPORTED
    elif average_change < Decimal("-0.02"):
        conclusion = OutcomeConclusion.NOT_SUPPORTED
    else:
        conclusion = OutcomeConclusion.INCONCLUSIVE
    interpretation = (
        f"Observed outcome is {conclusion.value}; this evaluation is "
        "associational and does not establish causation."
    )
    evaluation = recommendation.outcome_evaluation
    if evaluation is None:
        evaluation = RecommendationOutcomeEvaluation(
            recommendation_id=recommendation.id,
            conclusion=conclusion.value,
            average_relative_change=average_change,
            confidence=outcome_confidence,
            result_count=len(recommendation.results),
            interpretation=interpretation,
        )
        db.add(evaluation)
    else:
        evaluation.conclusion = conclusion.value
        evaluation.average_relative_change = average_change
        evaluation.confidence = outcome_confidence
        evaluation.result_count = len(recommendation.results)
        evaluation.interpretation = interpretation
        evaluation.evaluated_at = datetime.now(UTC)
    _commit(db, "Unable to evaluate outcome", "Unable to evaluate outcome")
    db.refresh(evaluation)
    return evaluation
