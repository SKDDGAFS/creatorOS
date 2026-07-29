from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode
from uuid import UUID

from pydantic import BaseModel, ConfigDict, SecretStr
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import (
    generate_pkce_verifier,
    generate_token,
    hash_token,
    pkce_s256_challenge,
)
from app.models.channel import Platform
from app.models.platform_integration import OAuthAuthorizationState
from app.platforms.credentials import (
    OAuthSecretStore,
    OAuthVerifierMaterial,
)
from app.services.errors import (
    AuthorizationError,
    InvalidRequestError,
    PersistenceError,
    ResourceNotFoundError,
    ServiceError,
)

GOOGLE_AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
YOUTUBE_READ_SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
YOUTUBE_ANALYTICS_SCOPE = "https://www.googleapis.com/auth/yt-analytics.readonly"
YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"


class OAuthStartResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    authorization_url: str
    expires_at: datetime


class ClaimedOAuthState(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    workspace_id: UUID
    user_id: UUID
    redirect_uri: str
    requested_scopes: tuple[str, ...]
    verifier: OAuthVerifierMaterial
    secret_reference: str


def _stored_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def requested_scopes(
    *,
    publishing: bool,
    settings: Settings,
) -> tuple[str, ...]:
    scopes = [YOUTUBE_READ_SCOPE, YOUTUBE_ANALYTICS_SCOPE]
    if publishing:
        if not settings.youtube_enable_publishing:
            raise InvalidRequestError(
                "YouTube publishing scope is disabled by configuration"
            )
        scopes.append(YOUTUBE_UPLOAD_SCOPE)
    return tuple(scopes)


def start_authorization(
    db: Session,
    *,
    secret_store: OAuthSecretStore,
    settings: Settings,
    workspace_id: UUID,
    user_id: UUID,
    publishing: bool,
) -> OAuthStartResponse:
    if settings.youtube_client_id is None or settings.youtube_client_secret is None:
        raise InvalidRequestError("YouTube OAuth is not configured")
    scopes = requested_scopes(publishing=publishing, settings=settings)
    state = generate_token()
    verifier_value = generate_pkce_verifier()
    verifier = OAuthVerifierMaterial(
        code_verifier=SecretStr(verifier_value),
    )
    reference = secret_store.store_oauth_verifier(
        workspace_id=workspace_id,
        platform=Platform.YOUTUBE,
        verifier=verifier,
    )
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.oauth_state_ttl_minutes)
    record = OAuthAuthorizationState(
        workspace_id=workspace_id,
        created_by_user_id=user_id,
        platform=Platform.YOUTUBE.value,
        state_hash=hash_token(state),
        secret_reference=reference,
        requested_scopes=list(scopes),
        redirect_uri=settings.youtube_oauth_redirect_uri,
        expires_at=expires_at,
    )
    db.add(record)
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        secret_store.delete_oauth_verifier(reference)
        raise PersistenceError("Unable to start YouTube authorization") from exc

    parameters = {
        "client_id": settings.youtube_client_id,
        "redirect_uri": settings.youtube_oauth_redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
        "state": state,
        "code_challenge": pkce_s256_challenge(verifier_value),
        "code_challenge_method": "S256",
    }
    return OAuthStartResponse(
        authorization_url=(f"{GOOGLE_AUTHORIZATION_ENDPOINT}?{urlencode(parameters)}"),
        expires_at=expires_at,
    )


def claim_callback_state(
    db: Session,
    *,
    secret_store: OAuthSecretStore,
    state: str,
    user_id: UUID,
    now: datetime | None = None,
) -> ClaimedOAuthState:
    claimed_at = now or datetime.now(UTC)
    record = db.scalar(
        select(OAuthAuthorizationState)
        .where(
            OAuthAuthorizationState.state_hash == hash_token(state),
            OAuthAuthorizationState.platform == Platform.YOUTUBE.value,
        )
        .with_for_update()
    )
    if record is None:
        db.rollback()
        raise ResourceNotFoundError("YouTube authorization state not found")
    if record.created_by_user_id != user_id:
        db.rollback()
        raise AuthorizationError("YouTube authorization state does not match user")
    if record.consumed_at is not None:
        db.rollback()
        raise AuthorizationError("YouTube authorization state was already used")
    if _stored_utc(record.expires_at) <= claimed_at:
        reference = record.secret_reference
        record.consumed_at = claimed_at
        try:
            db.commit()
        except SQLAlchemyError as exc:
            db.rollback()
            raise PersistenceError(
                "Unable to expire YouTube authorization state"
            ) from exc
        secret_store.delete_oauth_verifier(reference)
        raise AuthorizationError("YouTube authorization state expired")
    try:
        verifier = secret_store.load_oauth_verifier(record.secret_reference)
    except ServiceError:
        db.rollback()
        raise
    record.consumed_at = claimed_at
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise PersistenceError("Unable to claim YouTube authorization state") from exc
    return ClaimedOAuthState(
        workspace_id=record.workspace_id,
        user_id=record.created_by_user_id,
        redirect_uri=record.redirect_uri,
        requested_scopes=tuple(record.requested_scopes),
        verifier=verifier,
        secret_reference=record.secret_reference,
    )
