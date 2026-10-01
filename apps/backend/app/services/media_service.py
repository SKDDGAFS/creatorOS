from pathlib import Path
from typing import BinaryIO
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
LOCAL_EXTENSIONS = {
    ".mp4": ("video/mp4", ".mp4"),
    ".mov": ("video/quicktime", ".mov"),
    ".webm": ("video/webm", ".webm"),
    ".avi": ("video/x-msvideo", ".avi"),
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
    if upload.content_type not in ALLOWED_TYPES:
        raise ValueError("Unsupported video type; use MP4, MOV, WebM, or AVI")
    return _save_stream(
        db,
        channel_id=channel_id,
        source=upload.file,
        title=Path(upload.filename or "Untitled video").stem,
        media_type=upload.content_type,
        extension=EXTENSIONS[upload.content_type],
        storage_root=storage_root,
        max_size=max_size,
    )


def save_local_file(
    db: Session,
    *,
    channel_id: UUID,
    source_path: Path,
    storage_root: Path,
    max_size: int,
) -> Video:
    media_type = LOCAL_EXTENSIONS.get(source_path.suffix.lower())
    if media_type is None:
        raise ValueError("Unsupported video type; use MP4, MOV, WebM, or AVI")
    with source_path.open("rb") as source:
        return _save_stream(
            db,
            channel_id=channel_id,
            source=source,
            title=source_path.stem,
            media_type=media_type[0],
            extension=media_type[1],
            storage_root=storage_root,
            max_size=max_size,
        )


def _save_stream(
    db: Session,
    *,
    channel_id: UUID,
    source: BinaryIO,
    title: str,
    media_type: str,
    extension: str,
    storage_root: Path,
    max_size: int,
) -> Video:
    channel = db.get(Channel, channel_id)
    if channel is None:
        raise ResourceNotFoundError("Channel not found")
    storage_root.mkdir(parents=True, exist_ok=True)
    (storage_root / "videos").mkdir(parents=True, exist_ok=True)
    relative_path = Path("videos") / f"{uuid4().hex}{extension}"
    destination = (storage_root / relative_path).resolve()
    root = storage_root.resolve()
    if root not in destination.parents:
        raise ValueError("Invalid storage path")
    size = 0
    try:
        with destination.open("xb") as output:
            while chunk := source.read(1024 * 1024):
                size += len(chunk)
                if size > max_size:
                    raise ValueError(f"Video exceeds the {max_size} byte limit")
                output.write(chunk)
        video = Video(
            channel_id=channel_id,
            title=title[:500] or "Untitled video",
            media_path=relative_path.as_posix(),
            media_mime_type=media_type,
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


def ingest_watch_folder(
    db: Session,
    *,
    channel_id: UUID,
    watch_folder: Path,
    storage_root: Path,
    max_size: int,
) -> tuple[list[Video], list[dict[str, str]]]:
    if db.get(Channel, channel_id) is None:
        raise ResourceNotFoundError("Channel not found")

    watch_folder.mkdir(parents=True, exist_ok=True)
    processed_folder = watch_folder / "processed"
    imported: list[Video] = []
    skipped: list[dict[str, str]] = []

    for source_path in sorted(watch_folder.iterdir(), key=lambda path: path.name.lower()):
        if source_path.name == "processed" or not source_path.is_file():
            continue
        if source_path.is_symlink():
            skipped.append(
                {
                    "filename": source_path.name,
                    "reason": "Symbolic links are not imported",
                }
            )
            continue
        if source_path.suffix.lower() not in LOCAL_EXTENSIONS:
            skipped.append(
                {"filename": source_path.name, "reason": "Unsupported video type"}
            )
            continue

        try:
            video = save_local_file(
                db,
                channel_id=channel_id,
                source_path=source_path,
                storage_root=storage_root,
                max_size=max_size,
            )
            processed_folder.mkdir(exist_ok=True)
            archived_path = processed_folder / f"{uuid4().hex}_{source_path.name}"
            source_path.replace(archived_path)
            imported.append(video)
        except ValueError as exc:
            skipped.append({"filename": source_path.name, "reason": str(exc)})

    return imported, skipped
