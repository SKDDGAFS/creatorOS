from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.channel import Channel, Platform
from app.models.user import User
from app.schemas.channel import ChannelCreate, ChannelUpdate
from app.services.errors import (
    ConflictError,
    PersistenceError,
    ResourceNotFoundError,
)


def create_channel(db: Session, payload: ChannelCreate) -> Channel:
    if db.get(User, payload.user_id) is None:
        raise ResourceNotFoundError("User not found")

    values = payload.model_dump()
    values["platform"] = payload.platform.value
    channel = Channel(**values)
    db.add(channel)

    try:
        db.commit()
        db.refresh(channel)
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(
            "A channel with this platform and platform_channel_id already exists"
        ) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise PersistenceError("Unable to save channel") from exc

    return channel


def list_channels(
    db: Session,
    *,
    limit: int,
    offset: int,
    user_id: UUID | None = None,
    platform: Platform | None = None,
    is_active: bool | None = None,
) -> list[Channel]:
    statement: Select[tuple[Channel]] = select(Channel)

    if user_id is not None:
        statement = statement.where(Channel.user_id == user_id)
    if platform is not None:
        statement = statement.where(Channel.platform == platform.value)
    if is_active is not None:
        statement = statement.where(Channel.is_active == is_active)

    statement = statement.order_by(
        Channel.created_at.asc(),
        Channel.id.asc(),
    ).offset(offset).limit(limit)

    return list(db.scalars(statement).all())


def get_channel(db: Session, channel_id: UUID) -> Channel:
    channel = db.get(Channel, channel_id)
    if channel is None:
        raise ResourceNotFoundError("Channel not found")
    return channel


def update_channel(
    db: Session,
    channel_id: UUID,
    payload: ChannelUpdate,
) -> Channel:
    channel = get_channel(db, channel_id)
    changes = payload.model_dump(exclude_unset=True)

    if "platform" in changes:
        assert payload.platform is not None
        changes["platform"] = payload.platform.value

    for field_name, value in changes.items():
        setattr(channel, field_name, value)

    try:
        db.commit()
        db.refresh(channel)
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(
            "A channel with this platform and platform_channel_id already exists"
        ) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise PersistenceError("Unable to update channel") from exc

    return channel
