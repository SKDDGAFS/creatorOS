from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import (
    AuthContext,
    WorkspaceContext,
    get_auth_context,
    require_csrf,
    require_workspace_admin,
)
from app.db.session import get_db
from app.models.workspace import Workspace, WorkspaceMembership
from app.schemas.workspace import (
    MembershipCreate,
    MembershipResponse,
    WorkspaceCreate,
    WorkspaceResponse,
)
from app.services import workspace_service
from app.services.errors import AuthorizationError

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@router.get("", response_model=list[WorkspaceResponse])
def list_workspaces(
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[Session, Depends(get_db)],
) -> list[Workspace]:
    return workspace_service.list_workspaces(db, auth.user.id)


@router.post(
    "",
    response_model=WorkspaceResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_workspace(
    payload: WorkspaceCreate,
    auth: Annotated[AuthContext, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
) -> Workspace:
    return workspace_service.create_workspace(db, auth.user, payload.name)


@router.post(
    "/{workspace_id}/members",
    response_model=MembershipResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_member(
    workspace_id: UUID,
    payload: MembershipCreate,
    context: Annotated[WorkspaceContext, Depends(require_workspace_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> WorkspaceMembership:
    if workspace_id != context.workspace_id:
        raise AuthorizationError("Workspace access denied")
    return workspace_service.add_member(
        db,
        context.workspace_id,
        str(payload.email),
        payload.role,
    )
