from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import (
    WorkspaceContext,
    get_workspace_context,
    require_workspace_admin,
    require_workspace_write,
)
from app.db.session import get_db
from app.models.research import (
    Competitor,
    ContentIdea,
    ResearchFinding,
    ResearchHook,
    ResearchRun,
    ResearchRunStatus,
    ResearchSource,
)
from app.schemas.research import (
    CompetitorCreate,
    CompetitorResponse,
    ContentIdeaResponse,
    ResearchFindingResponse,
    ResearchHookResponse,
    ResearchRunCreate,
    ResearchRunResponse,
    ResearchSourceCreate,
    ResearchSourceResponse,
)
from app.services import research_service

router = APIRouter(prefix="/research", tags=["research"])


@router.post("/sources", response_model=ResearchSourceResponse)
def create_source(
    payload: ResearchSourceCreate,
    response: Response,
    context: Annotated[WorkspaceContext, Depends(require_workspace_write)],
    db: Annotated[Session, Depends(get_db)],
) -> ResearchSource:
    source, created = research_service.create_source(
        db,
        workspace_id=context.workspace_id,
        user_id=context.auth.user.id,
        payload=payload,
    )
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return source


@router.get("/sources", response_model=list[ResearchSourceResponse])
def list_sources(
    context: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ResearchSource]:
    return research_service.list_sources(
        db, workspace_id=context.workspace_id, limit=limit, offset=offset
    )


@router.post(
    "/competitors",
    response_model=CompetitorResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_competitor(
    payload: CompetitorCreate,
    context: Annotated[WorkspaceContext, Depends(require_workspace_write)],
    db: Annotated[Session, Depends(get_db)],
) -> Competitor:
    return research_service.create_competitor(
        db,
        workspace_id=context.workspace_id,
        user_id=context.auth.user.id,
        payload=payload,
    )


@router.get("/competitors", response_model=list[CompetitorResponse])
def list_competitors(
    context: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Competitor]:
    return research_service.list_competitors(
        db, workspace_id=context.workspace_id, limit=limit, offset=offset
    )


@router.post(
    "/runs",
    response_model=ResearchRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def schedule_research_run(
    payload: ResearchRunCreate,
    context: Annotated[WorkspaceContext, Depends(require_workspace_write)],
    db: Annotated[Session, Depends(get_db)],
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=8, max_length=200)
    ],
) -> ResearchRun:
    return research_service.schedule_run(
        db,
        workspace_id=context.workspace_id,
        user_id=context.auth.user.id,
        payload=payload,
        idempotency_key=idempotency_key,
    )


@router.get("/runs", response_model=list[ResearchRunResponse])
def list_research_runs(
    context: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    db: Annotated[Session, Depends(get_db)],
    run_status: Annotated[ResearchRunStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ResearchRun]:
    return research_service.list_runs(
        db,
        workspace_id=context.workspace_id,
        status=run_status,
        limit=limit,
        offset=offset,
    )


@router.get("/runs/{run_id}", response_model=ResearchRunResponse)
def get_research_run(
    run_id: UUID,
    context: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    db: Annotated[Session, Depends(get_db)],
) -> ResearchRun:
    return research_service.get_run(
        db, workspace_id=context.workspace_id, run_id=run_id
    )


@router.post("/runs/{run_id}/cancel", response_model=ResearchRunResponse)
def cancel_research_run(
    run_id: UUID,
    context: Annotated[WorkspaceContext, Depends(require_workspace_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> ResearchRun:
    return research_service.cancel_run(
        db,
        workspace_id=context.workspace_id,
        run_id=run_id,
        actor_user_id=context.auth.user.id,
    )


@router.get("/findings", response_model=list[ResearchFindingResponse])
def list_findings(
    context: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ResearchFinding]:
    return research_service.list_findings(
        db, workspace_id=context.workspace_id, limit=limit, offset=offset
    )


@router.get("/hooks", response_model=list[ResearchHookResponse])
def list_hooks(
    context: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ResearchHook]:
    return research_service.list_hooks(
        db, workspace_id=context.workspace_id, limit=limit, offset=offset
    )


@router.get("/content-ideas", response_model=list[ContentIdeaResponse])
def list_content_ideas(
    context: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ContentIdea]:
    return research_service.list_content_ideas(
        db, workspace_id=context.workspace_id, limit=limit, offset=offset
    )
