from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMembership, WorkspaceRole
from app.services.errors import (
    AuthorizationError,
    ConflictError,
    PersistenceError,
    ResourceNotFoundError,
)


def list_workspaces(db: Session, user_id: UUID) -> list[Workspace]:
    statement = (
        select(Workspace)
        .join(WorkspaceMembership)
        .where(WorkspaceMembership.user_id == user_id)
        .order_by(Workspace.created_at, Workspace.id)
    )
    return list(db.scalars(statement).all())


def create_workspace(db: Session, user: User, name: str) -> Workspace:
    workspace = Workspace(name=name)
    db.add(
        WorkspaceMembership(
            workspace=workspace,
            user=user,
            role=WorkspaceRole.OWNER.value,
        )
    )
    try:
        db.commit()
        db.refresh(workspace)
    except SQLAlchemyError as exc:
        db.rollback()
        raise PersistenceError("Unable to create workspace") from exc
    return workspace


def add_member(
    db: Session,
    workspace_id: UUID,
    email: str,
    role: WorkspaceRole,
) -> WorkspaceMembership:
    if role is WorkspaceRole.OWNER:
        raise AuthorizationError("Owner role cannot be assigned through this endpoint")
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None:
        raise ResourceNotFoundError("User not found")
    membership = WorkspaceMembership(
        workspace_id=workspace_id,
        user_id=user.id,
        role=role.value,
    )
    db.add(membership)
    try:
        db.commit()
        db.refresh(membership)
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("User is already a workspace member") from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise PersistenceError("Unable to add workspace member") from exc
    return membership
