import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from app.core.credentials import decrypt_credential, encrypt_credential
from app.db.base import Base, utc_now

if TYPE_CHECKING:
    from app.models.user import User


class EncryptedCredential(TypeDecorator[str]):
    impl = Text
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect: object) -> str | None:
        if value is None:
            return None
        return encrypt_credential(value)

    def process_result_value(self, value: str | None, dialect: object) -> str | None:
        if value is None:
            return None
        return decrypt_credential(value)


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (
        CheckConstraint(
            "platform IN ('youtube', 'tiktok', 'instagram')",
            name="platform_allowed",
        ),
        UniqueConstraint(
            "user_id",
            "platform",
            "channel_id",
            name="uq_accounts_user_platform_channel",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    platform: Mapped[str] = mapped_column(String(20))
    account_name: Mapped[str] = mapped_column(String(255))
    channel_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_connected: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    oauth_state: Mapped[str | None] = mapped_column(EncryptedCredential())
    scopes: Mapped[list[str]] = mapped_column(JSON, default=list, server_default="[]")
    access_token: Mapped[str | None] = mapped_column(EncryptedCredential())
    refresh_token: Mapped[str | None] = mapped_column(EncryptedCredential())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )

    user: Mapped[User] = relationship(back_populates="accounts")