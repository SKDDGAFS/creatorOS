from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.channel import Channel
from app.schemas.channel import ChannelResponse
from app.services.local_service import bootstrap_local_owner

router = APIRouter(prefix="/local", tags=["local setup"])


@router.post("/setup", response_model=list[ChannelResponse])
def setup_local_channels(db: Session = Depends(get_db)) -> list[Channel]:
    _, channels = bootstrap_local_owner(db)
    return channels
