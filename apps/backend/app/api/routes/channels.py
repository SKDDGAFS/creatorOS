from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.errors import raise_service_http_error
from app.db.session import get_db
from app.models.channel import Channel, Platform
from app.schemas.channel import ChannelCreate, ChannelResponse, ChannelUpdate
from app.services import channel_service
from app.services.errors import ServiceError

router = APIRouter(prefix="/channels", tags=["channels"])


@router.post(
    "",
    response_model=ChannelResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_channel(
    payload: ChannelCreate,
    db: Session = Depends(get_db),
) -> Channel:
    try:
        return channel_service.create_channel(db, payload)
    except ServiceError as exc:
        raise_service_http_error(exc)


@router.get("", response_model=list[ChannelResponse])
def list_channels(
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    user_id: UUID | None = None,
    platform: Platform | None = None,
    is_active: bool | None = None,
    db: Session = Depends(get_db),
) -> list[Channel]:
    return channel_service.list_channels(
        db,
        limit=limit,
        offset=offset,
        user_id=user_id,
        platform=platform,
        is_active=is_active,
    )


@router.get("/{channel_id}", response_model=ChannelResponse)
def get_channel(
    channel_id: UUID,
    db: Session = Depends(get_db),
) -> Channel:
    try:
        return channel_service.get_channel(db, channel_id)
    except ServiceError as exc:
        raise_service_http_error(exc)


@router.patch("/{channel_id}", response_model=ChannelResponse)
def update_channel(
    channel_id: UUID,
    payload: ChannelUpdate,
    db: Session = Depends(get_db),
) -> Channel:
    try:
        return channel_service.update_channel(db, channel_id, payload)
    except ServiceError as exc:
        raise_service_http_error(exc)
