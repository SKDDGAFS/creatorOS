from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode
from uuid import UUID

from pydantic import BaseModel, ConfigDict, SecretStr
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import generate_pkce_verifier, generate_token, hash_token
from app.models.channel import Platform
from app.models.platform_integration import OAuthAuthorizationState
from app.platforms.credentials import OAuthSecretStore, OAuthVerifierMaterial
from app.services.errors import (
    AuthorizationError,
    InvalidRequestError,
    PersistenceError,
    ResourceNotFoundError,
    ServiceError,
)

TIKTOK_AUTHORIZATION_ENDPOINT = "https://www.tiktok.com/v2/auth/authorize/"
TIKTOK_BASIC_SCOPE = "user.info.basic"
TIKTOK_PROFILE_SCOPE = "user.info.profile"
TIKTOK_STATS_SCOPE = "user.info.stats"
TIKTOK_VIDEO_SCOPE = "video.list"
TIKTOK_PUBLISH_SCOPE = "video.publish"


class OAuthStartResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    authorization_url: str
    expires_at: datetime


class ClaimedOAuthState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: UUID
    user_id: UUID
    redirect_uri: str
    requested_scopes: tuple[str, ...]
    secret_reference: str


def _stored_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def requested_scopes(
    *,
    publishing: bool,
    settings: Settings,
) -> tuple[str, ...]:
    scopes = [
        TIKTOK_BASIC_SCOPE,
        TIKTOK_PROFILE_SCOPE,
        TIKTOK_STATS_SCOPE,
        TIKTOK_VIDEO_SCOPE,
    ]
    if publishing:
        if not settings.tiktok_enable_publishing:
            raise InvalidRequestError("TikTok publishing permission is not enabled")
        scopes.append(TIKTOK_PUBLISH_SCOPE)
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
    if settings.tiktok_client_key is None or settings.tiktok_client_secret is None:
        raise InvalidRequestError("TikTok OAuth is not configured")
    scopes = requested_scopes(publishing=publishing, settings=settings)
    state = generate_token()
    proof = OAuthVerifierMaterial(
        code_verifier=SecretStr(generate_pkce_verifier()),
    )
    reference = secret_store.store_oauth_verifier(
        workspace_id=workspace_id,
        platform=Platform.TIKTOK,
        verifier=proof,
    )
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.oauth_state_ttl_minutes)
    record = OAuthAuthorizationState(
        workspace_id=workspace_id,
        created_by_user_id=user_id,
        platform=Platform.TIKTOK.value,
        state_hash=hash_token(state),
        secret_reference=reference,
        requested_scopes=list(scopes),
        redirect_uri=settings.tiktok_oauth_redirect_uri,
        expires_at=expires_at,
    )
    db.add(record)
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        secret_store.delete_oauth_verifier(reference)
        raise PersistenceError("Unable to start TikTok authorization") from exc

    parameters = {
        "client_key": settings.tiktok_client_key,
        "redirect_uri": settings.tiktok_oauth_redirect_uri,
        "response_type": "code",
        "scope": ",".join(scopes),
        "state": state,
        "disable_auto_auth": "1",
    }
    return OAuthStartResponse(
        authorization_url=(f"{TIKTOK_AUTHORIZATION_ENDPOINT}?{urlencode(parameters)}"),
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
            OAuthAuthorizationState.platform == Platform.TIKTOK.value,
        )
        .with_for_update()
    )
    if record is None:
        db.rollback()
        raise ResourceNotFoundError("TikTok authorization state not found")
    if record.created_by_user_id != user_id:
        db.rollback()
        raise AuthorizationError("TikTok authorization state does not match user")
    if record.consumed_at is not None:
        db.rollback()
        raise AuthorizationError("TikTok authorization state was already used")
    if _stored_utc(record.expires_at) <= claimed_at:
        reference = record.secret_reference
        record.consumed_at = claimed_at
        try:
            db.commit()
        except SQLAlchemyError as exc:
            db.rollback()
            raise PersistenceError(
                "Unable to expire TikTok authorization state"
            ) from exc
        secret_store.delete_oauth_verifier(reference)
        raise AuthorizationError("TikTok authorization state expired")
    try:
        secret_store.load_oauth_verifier(record.secret_reference)
    except ServiceError:
        db.rollback()
        raise
    record.consumed_at = claimed_at
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise PersistenceError("Unable to claim TikTok authorization state") from exc
    return ClaimedOAuthState(
        workspace_id=record.workspace_id,
        user_id=record.created_by_user_id,
        redirect_uri=record.redirect_uri,
        requested_scopes=tuple(record.requested_scopes),
        secret_reference=record.secret_reference,
    )
