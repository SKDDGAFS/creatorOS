import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utc_now


class AuthThrottle(Base):
    __tablename__ = "auth_throttles"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    identifier_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    failed_attempts: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
    )
    window_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
    )
    blocked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
