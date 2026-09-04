from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import (
    WorkspaceContext,
    get_workspace_context,
    require_workspace_write,
)
from app.db.session import get_db
from app.models.recommendation import (
    Recommendation,
    RecommendationOutcomeEvaluation,
    RecommendationResult,
    RecommendationStatus,
)
from app.schemas.recommendation import (
    OutcomeEvaluationResponse,
    RecommendationCreate,
    RecommendationResponse,
    RecommendationResultCreate,
    RecommendationResultResponse,
    RecommendationStatusUpdate,
)
from app.services import recommendation_service

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.post("", response_model=RecommendationResponse)
def create_recommendation(
    payload: RecommendationCreate,
    response: Response,
    context: Annotated[WorkspaceContext, Depends(require_workspace_write)],
    db: Annotated[Session, Depends(get_db)],
) -> Recommendation:
    recommendation, created = recommendation_service.create_recommendation(
        db,
        workspace_id=context.workspace_id,
        user_id=context.auth.user.id,
        payload=payload,
    )
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return recommendation


@router.get("", response_model=list[RecommendationResponse])
def list_recommendations(
    context: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    db: Annotated[Session, Depends(get_db)],
    recommendation_status: Annotated[
        RecommendationStatus | None, Query(alias="status")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Recommendation]:
    return recommendation_service.list_recommendations(
        db,
        workspace_id=context.workspace_id,
        status=recommendation_status,
        limit=limit,
        offset=offset,
    )


@router.get("/{recommendation_id}", response_model=RecommendationResponse)
def get_recommendation(
    recommendation_id: UUID,
    context: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    db: Annotated[Session, Depends(get_db)],
) -> Recommendation:
    return recommendation_service.get_recommendation(
        db,
        workspace_id=context.workspace_id,
        recommendation_id=recommendation_id,
    )


@router.post("/{recommendation_id}/status", response_model=RecommendationResponse)
def update_status(
    recommendation_id: UUID,
    payload: RecommendationStatusUpdate,
    context: Annotated[WorkspaceContext, Depends(require_workspace_write)],
    db: Annotated[Session, Depends(get_db)],
) -> Recommendation:
    return recommendation_service.transition_status(
        db,
        workspace_id=context.workspace_id,
        recommendation_id=recommendation_id,
        target=payload.status,
    )


@router.post(
    "/{recommendation_id}/results",
    response_model=RecommendationResultResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_result(
    recommendation_id: UUID,
    payload: RecommendationResultCreate,
    context: Annotated[WorkspaceContext, Depends(require_workspace_write)],
    db: Annotated[Session, Depends(get_db)],
) -> RecommendationResult:
    return recommendation_service.add_result(
        db,
        workspace_id=context.workspace_id,
        recommendation_id=recommendation_id,
        user_id=context.auth.user.id,
        payload=payload,
    )


@router.post(
    "/{recommendation_id}/evaluate",
    response_model=OutcomeEvaluationResponse,
)
def evaluate_outcome(
    recommendation_id: UUID,
    context: Annotated[WorkspaceContext, Depends(require_workspace_write)],
    db: Annotated[Session, Depends(get_db)],
) -> RecommendationOutcomeEvaluation:
    return recommendation_service.evaluate_outcome(
        db,
        workspace_id=context.workspace_id,
        recommendation_id=recommendation_id,
    )
