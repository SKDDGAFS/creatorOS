from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import (
    WorkspaceContext,
    get_workspace_context,
    require_workspace_admin,
    require_workspace_write,
)
from app.db.session import get_db
from app.models.ai import (
    AIInvocation,
    AIPromptVersion,
    AIProviderConfiguration,
    AIUsageBudget,
)
from app.schemas.ai import (
    AIInvocationResponse,
    AIPromptVersionCreate,
    AIPromptVersionResponse,
    AIProviderCreate,
    AIProviderHealthResponse,
    AIProviderResponse,
    AIUsageBudgetResponse,
    AIUsageBudgetUpdate,
    AIUsageSummary,
)
from app.services import ai_service

router = APIRouter(prefix="/ai", tags=["AI providers"])


@router.post(
    "/providers",
    response_model=AIProviderResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_provider(
    payload: AIProviderCreate,
    context: Annotated[WorkspaceContext, Depends(require_workspace_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> AIProviderConfiguration:
    return ai_service.create_provider_configuration(
        db,
        workspace_id=context.workspace_id,
        user_id=context.auth.user.id,
        payload=payload,
    )


@router.get("/providers", response_model=list[AIProviderResponse])
def list_providers(
    context: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    db: Annotated[Session, Depends(get_db)],
    include_disabled: Annotated[bool, Query()] = False,
) -> list[AIProviderConfiguration]:
    return ai_service.list_provider_configurations(
        db,
        workspace_id=context.workspace_id,
        include_disabled=include_disabled,
    )


@router.post(
    "/providers/{provider_id}/disable",
    response_model=AIProviderResponse,
)
def disable_provider(
    provider_id: UUID,
    context: Annotated[WorkspaceContext, Depends(require_workspace_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> AIProviderConfiguration:
    return ai_service.disable_provider_configuration(
        db,
        workspace_id=context.workspace_id,
        provider_id=provider_id,
    )


@router.get("/health", response_model=list[AIProviderHealthResponse])
def provider_health(
    context: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    db: Annotated[Session, Depends(get_db)],
) -> list[AIProviderHealthResponse]:
    return ai_service.check_provider_health(
        db,
        workspace_id=context.workspace_id,
    )


@router.post(
    "/prompts",
    response_model=AIPromptVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_prompt(
    payload: AIPromptVersionCreate,
    context: Annotated[WorkspaceContext, Depends(require_workspace_write)],
    db: Annotated[Session, Depends(get_db)],
) -> AIPromptVersion:
    return ai_service.create_prompt_version(
        db,
        workspace_id=context.workspace_id,
        user_id=context.auth.user.id,
        payload=payload,
    )


@router.get("/prompts", response_model=list[AIPromptVersionResponse])
def list_prompts(
    context: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    db: Annotated[Session, Depends(get_db)],
    name: Annotated[str | None, Query(max_length=100)] = None,
) -> list[AIPromptVersion]:
    return ai_service.list_prompt_versions(
        db,
        workspace_id=context.workspace_id,
        name=name,
    )


@router.put("/budget", response_model=AIUsageBudgetResponse)
def update_budget(
    payload: AIUsageBudgetUpdate,
    context: Annotated[WorkspaceContext, Depends(require_workspace_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> AIUsageBudget:
    return ai_service.upsert_usage_budget(
        db,
        workspace_id=context.workspace_id,
        payload=payload,
    )


@router.get("/usage", response_model=AIUsageSummary)
def get_usage(
    context: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    db: Annotated[Session, Depends(get_db)],
) -> AIUsageSummary:
    return ai_service.usage_summary(db, workspace_id=context.workspace_id)


@router.get("/invocations", response_model=list[AIInvocationResponse])
def list_invocations(
    context: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AIInvocation]:
    return ai_service.list_invocations(
        db,
        workspace_id=context.workspace_id,
        limit=limit,
        offset=offset,
    )
