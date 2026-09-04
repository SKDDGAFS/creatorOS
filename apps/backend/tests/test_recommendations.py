from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.recommendation import RecommendationStatus
from app.schemas.growth_signal import (
    GrowthSignalProfileCreate,
    GrowthSignalWeightCreate,
)
from app.schemas.recommendation import (
    RecommendationCreate,
    RecommendationEvidenceCreate,
    RecommendationResultCreate,
)
from app.services import growth_signal_service, recommendation_service
from app.services.errors import InvalidRequestError
from tests.test_core_apis import headers, register


def _profile(db: Session, auth: dict):
    return growth_signal_service.create_profile(
        db,
        workspace_id=UUID(auth["workspace_id"]),
        user_id=UUID(auth["user"]["id"]),
        payload=GrowthSignalProfileCreate(
            name="Recommendation weights",
            goal="increase watch time",
            weights=[
                GrowthSignalWeightCreate(
                    signal="completion_rate",
                    tier="strong",
                    weight=Decimal("10"),
                    minimum_sample_size=10,
                    full_confidence_sample_size=100,
                )
            ],
        ),
    )


def _payload(profile_id) -> RecommendationCreate:
    return RecommendationCreate(
        growth_signal_profile_id=profile_id,
        proposed_action="Test a result-first opening on the next three videos.",
        rationale="Completion is directionally stronger in the observed sample.",
        expected_effect="A modest improvement in completion rate.",
        uncertainty="Topic and audience mix may explain part of the association.",
        linked_goal="increase watch time",
        expected_impact="medium",
        effort_estimate="low",
        risk_level="low",
        evidence=(
            RecommendationEvidenceCreate(
                signal="completion_rate",
                metric_name="completion rate",
                normalized_value=Decimal("0.7"),
                sample_size=50,
                source_confidence=Decimal("0.8"),
                explanation="Observed across 50 comparable posts.",
            ),
        ),
    )


def test_recommendation_confidence_dedup_and_workspace_isolation(
    client: TestClient,
    db_session: Session,
) -> None:
    owner = register(client, "recommendation@example.com")
    profile = _profile(db_session, owner)
    created, was_created = recommendation_service.create_recommendation(
        db_session,
        workspace_id=UUID(owner["workspace_id"]),
        user_id=UUID(owner["user"]["id"]),
        payload=_payload(profile.id),
    )
    repeated, repeated_created = recommendation_service.create_recommendation(
        db_session,
        workspace_id=UUID(owner["workspace_id"]),
        user_id=UUID(owner["user"]["id"]),
        payload=_payload(profile.id),
    )

    assert was_created and not repeated_created
    assert repeated.id == created.id
    assert created.confidence == Decimal("0.400000")
    assert created.sample_size == 50
    with pytest.raises(ValueError):
        RecommendationCreate.model_validate(
            {
                **_payload(profile.id).model_dump(),
                "expected_effect": "This guarantees more views.",
            }
        )

    other = register(client, "recommendation-other@example.com")
    response = client.get("/api/recommendations", headers=headers(other))
    assert response.status_code == 200
    assert response.json() == []


def test_status_results_and_outcome_remain_correlational(
    client: TestClient,
    db_session: Session,
) -> None:
    auth = register(client, "recommendation-outcome@example.com")
    profile = _profile(db_session, auth)
    recommendation, _ = recommendation_service.create_recommendation(
        db_session,
        workspace_id=UUID(auth["workspace_id"]),
        user_id=UUID(auth["user"]["id"]),
        payload=_payload(profile.id),
    )
    for target in (RecommendationStatus.ACCEPTED, RecommendationStatus.IN_PROGRESS):
        recommendation_service.transition_status(
            db_session,
            workspace_id=UUID(auth["workspace_id"]),
            recommendation_id=recommendation.id,
            target=target,
        )
    with pytest.raises(InvalidRequestError):
        recommendation_service.transition_status(
            db_session,
            workspace_id=UUID(auth["workspace_id"]),
            recommendation_id=recommendation.id,
            target=RecommendationStatus.PROPOSED,
        )

    now = datetime.now(UTC)
    recommendation_service.add_result(
        db_session,
        workspace_id=UUID(auth["workspace_id"]),
        recommendation_id=recommendation.id,
        user_id=UUID(auth["user"]["id"]),
        payload=RecommendationResultCreate(
            metric_name="completion rate index",
            baseline_value=Decimal("100"),
            observed_value=Decimal("120"),
            sample_size=100,
            measurement_started_at=now - timedelta(days=7),
            measurement_ended_at=now,
        ),
    )
    evaluation = recommendation_service.evaluate_outcome(
        db_session,
        workspace_id=UUID(auth["workspace_id"]),
        recommendation_id=recommendation.id,
    )

    assert evaluation.conclusion == "supported"
    assert evaluation.average_relative_change == Decimal("0.200000")
    assert evaluation.confidence == Decimal("0.400000")
    assert "does not establish causation" in evaluation.interpretation
