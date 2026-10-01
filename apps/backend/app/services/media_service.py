from pathlib import Path
from uuid import UUID, uuid4

from fastapi import UploadFile
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.channel import Channel
from app.models.video import Video
from app.services.errors import PersistenceError, ResourceNotFoundError

ALLOWED_TYPES = {"video/mp4", "video/quicktime", "video/webm", "video/x-msvideo"}
EXTENSIONS = {
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
    "video/webm": ".webm",
    "video/x-msvideo": ".avi",
}


def _cleanup(destination: Path, storage_root: Path) -> None:
    destination.unlink(missing_ok=True)
    videos_root = storage_root / "videos"
    if videos_root.exists() and not any(videos_root.iterdir()):
        videos_root.rmdir()


def save_upload(
    db: Session,
    *,
    channel_id: UUID,
    upload: UploadFile,
    storage_root: Path,
    max_size: int,
) -> Video:
    channel = db.get(Channel, channel_id)
    if channel is None:
        raise ResourceNotFoundError("Channel not found")
    if upload.content_type not in ALLOWED_TYPES:
        raise ValueError("Unsupported video type; use MP4, MOV, WebM, or AVI")
    storage_root.mkdir(parents=True, exist_ok=True)
    (storage_root / "videos").mkdir(parents=True, exist_ok=True)
    relative_path = Path("videos") / f"{uuid4().hex}{EXTENSIONS[upload.content_type]}"
    destination = (storage_root / relative_path).resolve()
    root = storage_root.resolve()
    if root not in destination.parents:
        raise ValueError("Invalid storage path")
    size = 0
    try:
        with destination.open("xb") as output:
            while chunk := upload.file.read(1024 * 1024):
                size += len(chunk)
                if size > max_size:
                    raise ValueError(f"Video exceeds the {max_size} byte limit")
                output.write(chunk)
        video = Video(
            channel_id=channel_id,
            title=Path(upload.filename or "Untitled video").stem[:500]
            or "Untitled video",
            media_path=relative_path.as_posix(),
            media_mime_type=upload.content_type,
            media_size_bytes=size,
        )
        db.add(video)
        db.commit()
        db.refresh(video)
        return video
    except ValueError:
        db.rollback()
        _cleanup(destination, storage_root)
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        _cleanup(destination, storage_root)
        raise PersistenceError("Unable to save uploaded video") from exc
