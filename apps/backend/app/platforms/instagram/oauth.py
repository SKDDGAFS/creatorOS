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

INSTAGRAM_AUTHORIZATION_ENDPOINT = "https://www.instagram.com/oauth/authorize"
INSTAGRAM_BASIC_SCOPE = "instagram_business_basic"
INSTAGRAM_INSIGHTS_SCOPE = "instagram_business_manage_insights"
INSTAGRAM_PUBLISH_SCOPE = "instagram_business_content_publish"


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
    scopes = [INSTAGRAM_BASIC_SCOPE, INSTAGRAM_INSIGHTS_SCOPE]
    if publishing:
        if not settings.instagram_enable_publishing:
            raise InvalidRequestError(
                "Instagram publishing permission is not enabled"
            )
        scopes.append(INSTAGRAM_PUBLISH_SCOPE)
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
    if settings.instagram_app_id is None or settings.instagram_app_secret is None:
        raise InvalidRequestError("Instagram OAuth is not configured")
    scopes = requested_scopes(publishing=publishing, settings=settings)
    state = generate_token()
    proof = OAuthVerifierMaterial(
        code_verifier=SecretStr(generate_pkce_verifier()),
    )
    reference = secret_store.store_oauth_verifier(
        workspace_id=workspace_id,
        platform=Platform.INSTAGRAM,
        verifier=proof,
    )
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.oauth_state_ttl_minutes)
    record = OAuthAuthorizationState(
        workspace_id=workspace_id,
        created_by_user_id=user_id,
        platform=Platform.INSTAGRAM.value,
        state_hash=hash_token(state),
        secret_reference=reference,
        requested_scopes=list(scopes),
        redirect_uri=settings.instagram_oauth_redirect_uri,
        expires_at=expires_at,
    )
    db.add(record)
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        secret_store.delete_oauth_verifier(reference)
        raise PersistenceError("Unable to start Instagram authorization") from exc

    parameters = {
        "client_id": settings.instagram_app_id,
        "redirect_uri": settings.instagram_oauth_redirect_uri,
        "response_type": "code",
        "scope": ",".join(scopes),
        "state": state,
        "enable_fb_login": "0",
        "force_authentication": "1",
    }
    return OAuthStartResponse(
        authorization_url=(
            f"{INSTAGRAM_AUTHORIZATION_ENDPOINT}?{urlencode(parameters)}"
        ),
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
            OAuthAuthorizationState.platform == Platform.INSTAGRAM.value,
        )
        .with_for_update()
    )
    if record is None:
        db.rollback()
        raise ResourceNotFoundError("Instagram authorization state not found")
    if record.created_by_user_id != user_id:
        db.rollback()
        raise AuthorizationError(
            "Instagram authorization state does not match user"
        )
    if record.consumed_at is not None:
        db.rollback()
        raise AuthorizationError(
            "Instagram authorization state was already used"
        )
    if _stored_utc(record.expires_at) <= claimed_at:
        reference = record.secret_reference
        record.consumed_at = claimed_at
        try:
            db.commit()
        except SQLAlchemyError as exc:
            db.rollback()
            raise PersistenceError(
                "Unable to expire Instagram authorization state"
            ) from exc
        secret_store.delete_oauth_verifier(reference)
        raise AuthorizationError("Instagram authorization state expired")
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
        raise PersistenceError(
            "Unable to claim Instagram authorization state"
        ) from exc
    return ClaimedOAuthState(
        workspace_id=record.workspace_id,
        user_id=record.created_by_user_id,
        redirect_uri=record.redirect_uri,
        requested_scopes=tuple(record.requested_scopes),
        secret_reference=record.secret_reference,
    )
