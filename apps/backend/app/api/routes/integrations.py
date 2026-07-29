from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import (
    AuthContext,
    WorkspaceContext,
    get_auth_context,
    get_workspace_context,
    require_workspace_admin,
    require_workspace_write,
)
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models.channel import Channel, Platform
from app.models.platform_integration import (
    PlatformConnection,
    PlatformQuotaUsage,
)
from app.models.video_metric import VideoMetric
from app.platforms.credentials import InMemoryPlatformSecretStore
from app.platforms.runtime import (
    YouTubeAdapterFactory,
    get_platform_secret_store,
    get_youtube_adapter_factory,
)
from app.platforms.youtube import OAuthStartResponse
from app.schemas.channel import ChannelResponse
from app.schemas.platform_integration import (
    PlatformConnectionResponse,
    PlatformQuotaUsageResponse,
    VideoSyncResponse,
    YouTubeOAuthStartRequest,
)
from app.schemas.video import VideoResponse
from app.schemas.video_metric import VideoMetricResponse
from app.services import platform_integration_service, youtube_service

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.get("", response_model=list[PlatformConnectionResponse])
def list_integrations(
    context: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    db: Annotated[Session, Depends(get_db)],
    include_disconnected: bool = False,
) -> list[PlatformConnection]:
    return platform_integration_service.list_connections(
        db,
        workspace_id=context.workspace_id,
        platform=None,
        include_disconnected=include_disconnected,
    )


@router.post(
    "/youtube/oauth/start",
    response_model=OAuthStartResponse,
    status_code=status.HTTP_201_CREATED,
)
def start_youtube_oauth(
    payload: YouTubeOAuthStartRequest,
    context: Annotated[WorkspaceContext, Depends(require_workspace_admin)],
    db: Annotated[Session, Depends(get_db)],
    secret_store: Annotated[
        InMemoryPlatformSecretStore,
        Depends(get_platform_secret_store),
    ],
    settings: Annotated[Settings, Depends(get_settings)],
) -> OAuthStartResponse:
    return youtube_service.begin_authorization(
        db,
        secret_store=secret_store,
        settings=settings,
        workspace_id=context.workspace_id,
        user_id=context.auth.user.id,
        publishing=payload.publishing,
    )


@router.get(
    "/youtube/oauth/callback",
    response_model=PlatformConnectionResponse,
)
def complete_youtube_oauth(
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[Session, Depends(get_db)],
    secret_store: Annotated[
        InMemoryPlatformSecretStore,
        Depends(get_platform_secret_store),
    ],
    adapter_factory: Annotated[
        YouTubeAdapterFactory,
        Depends(get_youtube_adapter_factory),
    ],
    state_value: Annotated[
        str,
        Query(alias="state", min_length=20, max_length=500),
    ],
    code: Annotated[str | None, Query(min_length=1, max_length=4096)] = None,
    error: Annotated[str | None, Query(max_length=200)] = None,
) -> PlatformConnection:
    return youtube_service.complete_authorization(
        db,
        secret_store=secret_store,
        adapter_factory=adapter_factory,
        state=state_value,
        authorization_code=code,
        provider_error=error,
        user_id=auth.user.id,
    )


@router.get(
    "/youtube/{connection_id}",
    response_model=PlatformConnectionResponse,
)
def get_youtube_connection(
    connection_id: UUID,
    context: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    db: Annotated[Session, Depends(get_db)],
) -> PlatformConnection:
    return youtube_service.get_connection(
        db,
        workspace_id=context.workspace_id,
        connection_id=connection_id,
    )


@router.post(
    "/youtube/{connection_id}/sync/channel",
    response_model=ChannelResponse,
)
def sync_youtube_channel(
    connection_id: UUID,
    context: Annotated[WorkspaceContext, Depends(require_workspace_write)],
    db: Annotated[Session, Depends(get_db)],
    secret_store: Annotated[
        InMemoryPlatformSecretStore,
        Depends(get_platform_secret_store),
    ],
    adapter_factory: Annotated[
        YouTubeAdapterFactory,
        Depends(get_youtube_adapter_factory),
    ],
) -> Channel:
    return youtube_service.sync_channel(
        db,
        workspace_id=context.workspace_id,
        connection_id=connection_id,
        secret_store=secret_store,
        adapter_factory=adapter_factory,
    )


@router.post(
    "/youtube/{connection_id}/sync/videos",
    response_model=VideoSyncResponse,
)
def sync_youtube_videos(
    connection_id: UUID,
    context: Annotated[WorkspaceContext, Depends(require_workspace_write)],
    db: Annotated[Session, Depends(get_db)],
    secret_store: Annotated[
        InMemoryPlatformSecretStore,
        Depends(get_platform_secret_store),
    ],
    adapter_factory: Annotated[
        YouTubeAdapterFactory,
        Depends(get_youtube_adapter_factory),
    ],
) -> VideoSyncResponse:
    result = youtube_service.sync_videos(
        db,
        workspace_id=context.workspace_id,
        connection_id=connection_id,
        secret_store=secret_store,
        adapter_factory=adapter_factory,
    )
    return VideoSyncResponse(
        videos=[VideoResponse.model_validate(video) for video in result.videos],
        next_cursor=result.next_cursor,
    )


@router.post(
    "/youtube/{connection_id}/sync/videos/{video_id}/metrics",
    response_model=list[VideoMetricResponse],
)
def sync_youtube_metrics(
    connection_id: UUID,
    video_id: UUID,
    context: Annotated[WorkspaceContext, Depends(require_workspace_write)],
    db: Annotated[Session, Depends(get_db)],
    secret_store: Annotated[
        InMemoryPlatformSecretStore,
        Depends(get_platform_secret_store),
    ],
    adapter_factory: Annotated[
        YouTubeAdapterFactory,
        Depends(get_youtube_adapter_factory),
    ],
) -> list[VideoMetric]:
    return list(
        youtube_service.sync_metrics(
            db,
            workspace_id=context.workspace_id,
            connection_id=connection_id,
            video_id=video_id,
            secret_store=secret_store,
            adapter_factory=adapter_factory,
        )
    )


@router.get(
    "/youtube/{connection_id}/quota",
    response_model=list[PlatformQuotaUsageResponse],
)
def list_youtube_quota(
    connection_id: UUID,
    context: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    db: Annotated[Session, Depends(get_db)],
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[PlatformQuotaUsage]:
    connection = youtube_service.get_connection(
        db,
        workspace_id=context.workspace_id,
        connection_id=connection_id,
    )
    if connection.platform != Platform.YOUTUBE.value:
        return []
    return platform_integration_service.list_quota_usage(
        db,
        workspace_id=context.workspace_id,
        connection_id=connection_id,
        start_date=start_date,
        end_date=end_date,
    )


@router.delete(
    "/youtube/{connection_id}",
    response_model=PlatformConnectionResponse,
)
def disconnect_youtube(
    connection_id: UUID,
    context: Annotated[WorkspaceContext, Depends(require_workspace_admin)],
    db: Annotated[Session, Depends(get_db)],
    secret_store: Annotated[
        InMemoryPlatformSecretStore,
        Depends(get_platform_secret_store),
    ],
    adapter_factory: Annotated[
        YouTubeAdapterFactory,
        Depends(get_youtube_adapter_factory),
    ],
) -> PlatformConnection:
    return youtube_service.disconnect(
        db,
        workspace_id=context.workspace_id,
        connection_id=connection_id,
        secret_store=secret_store,
        adapter_factory=adapter_factory,
    )
