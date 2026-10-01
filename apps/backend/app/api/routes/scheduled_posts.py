from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.errors import raise_service_http_error
from app.db.session import get_db
from app.models.scheduled_post import ScheduledPost, ScheduledPostStatus
from app.schemas.scheduled_post import (
    ScheduledPostCreate,
    ScheduledPostResponse,
    ScheduledPostUpdate,
)
from app.services import scheduled_post_service
from app.services.errors import ServiceError

router = APIRouter(prefix="/scheduled-posts", tags=["scheduled posts"])


@router.post(
    "", response_model=ScheduledPostResponse, status_code=status.HTTP_201_CREATED
)
def create_post(
    payload: ScheduledPostCreate, db: Session = Depends(get_db)
) -> ScheduledPost:
    try:
        return scheduled_post_service.create_post(db, payload)
    except ServiceError as exc:
        raise_service_http_error(exc)


@router.get("", response_model=list[ScheduledPostResponse])
def list_posts(
    post_status: Annotated[ScheduledPostStatus | None, Query(alias="status")] = None,
    db: Session = Depends(get_db),
) -> list[ScheduledPost]:
    return scheduled_post_service.list_posts(db, post_status)


@router.patch("/{post_id}", response_model=ScheduledPostResponse)
def update_post(
    post_id: UUID, payload: ScheduledPostUpdate, db: Session = Depends(get_db)
) -> ScheduledPost:
    try:
        return scheduled_post_service.update_post(db, post_id, payload)
    except ServiceError as exc:
        raise_service_http_error(exc)
