from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import (
    WorkspaceContext,
    get_workspace_context,
    require_workspace_write,
)
from app.db.session import get_db
from app.models.channel import Channel, Platform
from app.schemas.channel import ChannelCreate, ChannelResponse, ChannelUpdate
from app.services import channel_service

router = APIRouter(prefix="/channels", tags=["channels"])


@router.post(
    "",
    response_model=ChannelResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_channel(
    payload: ChannelCreate,
    context: Annotated[WorkspaceContext, Depends(require_workspace_write)],
    db: Annotated[Session, Depends(get_db)],
) -> Channel:
    return channel_service.create_channel(
        db,
        payload,
        user_id=context.auth.user.id,
        workspace_id=context.workspace_id,
    )


@router.get("", response_model=list[ChannelResponse])
def list_channels(
    context: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    platform: Platform | None = None,
    is_active: bool | None = None,
) -> list[Channel]:
    return channel_service.list_channels(
        db,
        limit=limit,
        offset=offset,
        workspace_id=context.workspace_id,
        platform=platform,
        is_active=is_active,
    )


@router.get("/{channel_id}", response_model=ChannelResponse)
def get_channel(
    channel_id: UUID,
    context: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    db: Annotated[Session, Depends(get_db)],
) -> Channel:
    return channel_service.get_channel(
        db,
        channel_id,
        workspace_id=context.workspace_id,
    )


@router.patch("/{channel_id}", response_model=ChannelResponse)
def update_channel(
    channel_id: UUID,
    payload: ChannelUpdate,
    context: Annotated[WorkspaceContext, Depends(require_workspace_write)],
    db: Annotated[Session, Depends(get_db)],
) -> Channel:
    return channel_service.update_channel(
        db,
        channel_id,
        payload,
        workspace_id=context.workspace_id,
    )
