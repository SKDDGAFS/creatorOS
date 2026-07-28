from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import Cookie, Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_token, tokens_match
from app.db.session import get_db
from app.models.auth_session import AuthSession
from app.models.user import User
from app.models.workspace import WorkspaceMembership, WorkspaceRole
from app.services.errors import AuthenticationError, AuthorizationError

_settings = get_settings()


@dataclass(frozen=True)
class AuthContext:
    user: User
    session: AuthSession


@dataclass(frozen=True)
class WorkspaceContext:
    auth: AuthContext
    membership: WorkspaceMembership

    @property
    def workspace_id(self) -> UUID:
        return self.membership.workspace_id


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def get_auth_context(
    db: Annotated[Session, Depends(get_db)],
    session_token: Annotated[
        str | None,
        Cookie(alias=_settings.session_cookie_name),
    ] = None,
) -> AuthContext:
    if not session_token:
        raise AuthenticationError("Authentication required")
    session = db.scalar(
        select(AuthSession).where(AuthSession.token_hash == hash_token(session_token))
    )
    if (
        session is None
        or session.revoked_at is not None
        or _as_utc(session.expires_at) <= datetime.now(UTC)
    ):
        raise AuthenticationError("Authentication required")
    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("Authentication required")
    session.last_seen_at = datetime.now(UTC)
    db.commit()
    return AuthContext(user=user, session=session)


def require_csrf(
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    csrf_cookie: Annotated[
        str | None,
        Cookie(alias=_settings.csrf_cookie_name),
    ] = None,
    csrf_header: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> AuthContext:
    if (
        not csrf_cookie
        or not csrf_header
        or not tokens_match(csrf_cookie, csrf_header)
        or not tokens_match(hash_token(csrf_header), auth.session.csrf_token_hash)
    ):
        raise AuthorizationError("CSRF validation failed")
    return auth


def get_workspace_context(
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[Session, Depends(get_db)],
    active_workspace_id: Annotated[UUID, Header(alias="X-Workspace-ID")],
) -> WorkspaceContext:
    membership = db.scalar(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == active_workspace_id,
            WorkspaceMembership.user_id == auth.user.id,
        )
    )
    if membership is None:
        raise AuthorizationError("Workspace access denied")
    return WorkspaceContext(auth=auth, membership=membership)


def require_workspace_write(
    context: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    csrf_auth: Annotated[AuthContext, Depends(require_csrf)],
) -> WorkspaceContext:
    del csrf_auth
    if context.membership.role == WorkspaceRole.VIEWER.value:
        raise AuthorizationError("Workspace write access denied")
    return context


def require_workspace_admin(
    context: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    csrf_auth: Annotated[AuthContext, Depends(require_csrf)],
) -> WorkspaceContext:
    del csrf_auth
    if context.membership.role not in {
        WorkspaceRole.OWNER.value,
        WorkspaceRole.ADMIN.value,
    }:
        raise AuthorizationError("Workspace administration access denied")
    return context
