from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import (
    AuthContext,
    WorkspaceContext,
    get_auth_context,
    get_workspace_context,
    require_workspace_admin,
    require_workspace_write,
)
from app.db.session import get_db
from app.models.growth_signal import GrowthSignalProfile
from app.schemas.growth_signal import (
    GrowthScoreRequest,
    GrowthScoreResponse,
    GrowthSignalCatalogItem,
    GrowthSignalProfileCreate,
    GrowthSignalProfileResponse,
)
from app.services import growth_signal_service

router = APIRouter(prefix="/growth-signals", tags=["growth signals"])


@router.get("/catalog", response_model=list[GrowthSignalCatalogItem])
def get_signal_catalog(
    _auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> list[GrowthSignalCatalogItem]:
    return growth_signal_service.signal_catalog()


@router.post(
    "/profiles",
    response_model=GrowthSignalProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_profile(
    payload: GrowthSignalProfileCreate,
    context: Annotated[WorkspaceContext, Depends(require_workspace_write)],
    db: Annotated[Session, Depends(get_db)],
) -> GrowthSignalProfile:
    return growth_signal_service.create_profile(
        db,
        workspace_id=context.workspace_id,
        user_id=context.auth.user.id,
        payload=payload,
    )


@router.get(
    "/profiles",
    response_model=list[GrowthSignalProfileResponse],
)
def list_profiles(
    context: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    db: Annotated[Session, Depends(get_db)],
    include_inactive: Annotated[bool, Query()] = False,
) -> list[GrowthSignalProfile]:
    return growth_signal_service.list_profiles(
        db,
        workspace_id=context.workspace_id,
        include_inactive=include_inactive,
    )


@router.get(
    "/profiles/{profile_id}",
    response_model=GrowthSignalProfileResponse,
)
def get_profile(
    profile_id: UUID,
    context: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    db: Annotated[Session, Depends(get_db)],
) -> GrowthSignalProfile:
    return growth_signal_service.get_profile(
        db,
        workspace_id=context.workspace_id,
        profile_id=profile_id,
    )


@router.post(
    "/profiles/{profile_id}/score",
    response_model=GrowthScoreResponse,
)
def score_profile(
    profile_id: UUID,
    payload: GrowthScoreRequest,
    context: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    db: Annotated[Session, Depends(get_db)],
) -> GrowthScoreResponse:
    return growth_signal_service.score_profile(
        db,
        workspace_id=context.workspace_id,
        profile_id=profile_id,
        payload=payload,
    )


@router.post(
    "/profiles/{profile_id}/deactivate",
    response_model=GrowthSignalProfileResponse,
)
def deactivate_profile(
    profile_id: UUID,
    context: Annotated[WorkspaceContext, Depends(require_workspace_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> GrowthSignalProfile:
    return growth_signal_service.deactivate_profile(
        db,
        workspace_id=context.workspace_id,
        profile_id=profile_id,
    )
