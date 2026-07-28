import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import generate_token, hash_password, hash_token, verify_password
from app.models.auth_session import AuthSession
from app.models.auth_throttle import AuthThrottle
from app.models.password_reset_token import PasswordResetToken
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMembership, WorkspaceRole
from app.schemas.auth import RegisterRequest
from app.services.errors import (
    AuthenticationError,
    ConflictError,
    PersistenceError,
    RateLimitError,
)


@dataclass(frozen=True)
class IssuedSession:
    session: AuthSession
    session_token: str
    csrf_token: str


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _identifier_hash(email: str) -> str:
    return hashlib.sha256(_normalize_email(email).encode()).hexdigest()


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def register_user(db: Session, payload: RegisterRequest) -> tuple[User, Workspace]:
    user = User(
        email=_normalize_email(str(payload.email)),
        display_name=payload.display_name,
        password_hash=hash_password(payload.password),
        is_active=True,
    )
    workspace = Workspace(name=f"{payload.display_name}'s Workspace")
    membership = WorkspaceMembership(
        workspace=workspace,
        user=user,
        role=WorkspaceRole.OWNER.value,
    )
    db.add_all([user, workspace, membership])
    try:
        db.commit()
        db.refresh(user)
        db.refresh(workspace)
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("An account with this email already exists") from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise PersistenceError("Unable to create account") from exc
    return user, workspace


def _get_throttle(db: Session, email: str) -> AuthThrottle | None:
    return db.scalar(
        select(AuthThrottle).where(
            AuthThrottle.identifier_hash == _identifier_hash(email)
        )
    )


def authenticate(db: Session, email: str, password: str) -> User:
    settings = get_settings()
    now = datetime.now(UTC)
    throttle = _get_throttle(db, email)
    if (
        throttle
        and throttle.blocked_until
        and _as_utc(throttle.blocked_until) > now
    ):
        raise RateLimitError("Too many login attempts; try again later")

    user = db.scalar(select(User).where(User.email == _normalize_email(email)))
    valid = verify_password(password, user.password_hash if user else None)
    if not valid or user is None or not user.is_active:
        if throttle is None:
            throttle = AuthThrottle(
                identifier_hash=_identifier_hash(email),
                failed_attempts=0,
                window_started_at=now,
            )
            db.add(throttle)
        window = timedelta(minutes=settings.login_window_minutes)
        if now - _as_utc(throttle.window_started_at) > window:
            throttle.window_started_at = now
            throttle.failed_attempts = 0
        throttle.failed_attempts += 1
        if throttle.failed_attempts >= settings.login_max_failures:
            throttle.blocked_until = now + timedelta(
                minutes=settings.login_block_minutes
            )
        db.commit()
        raise AuthenticationError("Invalid email or password")

    if throttle is not None:
        db.delete(throttle)
        db.commit()
    return user


def issue_session(db: Session, user: User) -> IssuedSession:
    settings = get_settings()
    session_token = generate_token()
    csrf_token = generate_token()
    session = AuthSession(
        user_id=user.id,
        token_hash=hash_token(session_token),
        csrf_token_hash=hash_token(csrf_token),
        expires_at=datetime.now(UTC) + timedelta(hours=settings.session_ttl_hours),
    )
    db.add(session)
    try:
        db.commit()
        db.refresh(session)
    except SQLAlchemyError as exc:
        db.rollback()
        raise PersistenceError("Unable to create session") from exc
    return IssuedSession(session, session_token, csrf_token)


def revoke_session(db: Session, session: AuthSession) -> None:
    session.revoked_at = datetime.now(UTC)
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise PersistenceError("Unable to revoke session") from exc


def issue_password_reset(db: Session, user: User) -> str:
    settings = get_settings()
    token = generate_token()
    reset = PasswordResetToken(
        user_id=user.id,
        token_hash=hash_token(token),
        expires_at=datetime.now(UTC)
        + timedelta(minutes=settings.password_reset_ttl_minutes),
    )
    db.add(reset)
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise PersistenceError("Unable to create password reset request") from exc
    return token
