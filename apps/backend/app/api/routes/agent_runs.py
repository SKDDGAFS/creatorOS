from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.orm import Session

from app.agents import default_agent_registry
from app.api.dependencies.auth import (
    WorkspaceContext,
    get_workspace_context,
    require_workspace_admin,
    require_workspace_write,
)
from app.db.session import get_db
from app.models.agent_run import AgentRun, AgentRunStatus, AgentType
from app.schemas.agent_run import (
    AgentCapabilityResponse,
    AgentRunCreate,
    AgentRunResponse,
)
from app.services import agent_run_service

router = APIRouter(prefix="/agent-runs", tags=["agent runs"])


@router.get("/capabilities", response_model=list[AgentCapabilityResponse])
def list_agent_capabilities(
    context: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> list[AgentCapabilityResponse]:
    del context
    return [
        AgentCapabilityResponse(
            agent_type=item.agent_type,
            prompt_name=item.prompt_name,
            capability_tier=item.capability_tier,
            purpose=item.purpose,
            output_mode=item.output_mode,
            can_publish=item.can_publish,
            can_execute_shell=item.can_execute_shell,
        )
        for item in default_agent_registry().list()
    ]


@router.post(
    "",
    response_model=AgentRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_agent_run(
    payload: AgentRunCreate,
    context: Annotated[WorkspaceContext, Depends(require_workspace_write)],
    db: Annotated[Session, Depends(get_db)],
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=8, max_length=200),
    ],
) -> AgentRun:
    return agent_run_service.schedule_run(
        db,
        workspace_id=context.workspace_id,
        requested_by_user_id=context.auth.user.id,
        payload=payload,
        idempotency_key=idempotency_key,
    )


@router.get("", response_model=list[AgentRunResponse])
def list_agent_runs(
    context: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    db: Annotated[Session, Depends(get_db)],
    agent_type: AgentType | None = None,
    run_status: Annotated[AgentRunStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AgentRun]:
    return agent_run_service.list_runs(
        db,
        workspace_id=context.workspace_id,
        agent_type=agent_type,
        status=run_status,
        limit=limit,
        offset=offset,
    )


@router.get("/{run_id}", response_model=AgentRunResponse)
def get_agent_run(
    run_id: UUID,
    context: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    db: Annotated[Session, Depends(get_db)],
) -> AgentRun:
    return agent_run_service.get_run(
        db,
        workspace_id=context.workspace_id,
        run_id=run_id,
    )


@router.post("/{run_id}/cancel", response_model=AgentRunResponse)
def cancel_agent_run(
    run_id: UUID,
    context: Annotated[WorkspaceContext, Depends(require_workspace_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> AgentRun:
    return agent_run_service.cancel_run(
        db,
        workspace_id=context.workspace_id,
        run_id=run_id,
        actor_user_id=context.auth.user.id,
    )
