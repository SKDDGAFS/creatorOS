from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.channel import Channel, Platform
from app.models.user import User

LOCAL_EMAIL = "local@creatoros.invalid"


def bootstrap_local_owner(db: Session) -> tuple[User, list[Channel]]:
    user = db.scalar(select(User).where(User.email == LOCAL_EMAIL))
    if user is None:
        user = User(email=LOCAL_EMAIL, display_name="Local Creator")
        db.add(user)
        db.flush()

    channels: list[Channel] = []
    for platform in (Platform.YOUTUBE, Platform.INSTAGRAM, Platform.TIKTOK):
        channel = db.scalar(
            select(Channel).where(
                Channel.user_id == user.id,
                Channel.platform == platform.value,
                Channel.platform_channel_id == f"local-{platform.value}",
            )
        )
        if channel is None:
            channel = Channel(
                user_id=user.id,
                platform=platform.value,
                platform_channel_id=f"local-{platform.value}",
                name=f"Local {platform.value.title()}",
                is_authorized=False,
            )
            db.add(channel)
        channels.append(channel)
    db.commit()
    for channel in channels:
        db.refresh(channel)
    db.refresh(user)
    return user, channels
