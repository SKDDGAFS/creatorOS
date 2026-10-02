from pathlib import Path
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.video import Video
from app.providers.ai.base import AIProvider
from app.services.errors import ConflictError, PersistenceError
from app.services.video_service import get_video


def prepare_video(
    db: Session,
    video_id: UUID,
    *,
    provider: AIProvider,
    storage_root: Path,
) -> Video:
    video = get_video(db, video_id)
    if video.media_path is None:
        raise ConflictError("Video has no local media file")

    root = storage_root.resolve()
    media_path = (root / video.media_path).resolve()
    if root not in media_path.parents:
        raise ConflictError("Video media path is outside local storage")
    if not media_path.is_file():
        raise ConflictError("Video media file is unavailable")

    transcript = provider.transcribe(media_path)
    analysis = provider.analyze_video(transcript)
    metadata = provider.generate_metadata(
        transcript,
        analysis,
        video.channel.platform,
    )
    try:
        video.transcript = transcript
        video.ai_analysis = analysis
        video.draft_metadata = {"platform": video.channel.platform, "fields": metadata}
        db.commit()
        db.refresh(video)
    except SQLAlchemyError as error:
        db.rollback()
        raise PersistenceError("Unable to save local video preparation") from error
    return video
