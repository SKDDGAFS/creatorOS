from cryptography.fernet import Fernet
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.db.base import Base
from app.models import Account, User


def test_account_credentials_are_encrypted_in_database(monkeypatch) -> None:
    encryption_key = Fernet.generate_key().decode("ascii")
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", encryption_key)
    get_settings.cache_clear()
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)

    try:
        with Session(engine) as session:
            user = User(email="local@example.test", display_name="Local")
            account = Account(
                user=user,
                platform="youtube",
                account_name="Creator",
                channel_id="channel-123",
                oauth_state="state-secret",
                scopes=["upload"],
                access_token="access-secret",
                refresh_token="refresh-secret",
            )
            session.add_all([user, account])
            session.flush()

            stored = session.execute(
                text(
                    "SELECT oauth_state, access_token, refresh_token "
                    "FROM accounts"
                )
            ).one()
            assert "state-secret" not in stored.oauth_state
            assert "access-secret" not in stored.access_token
            assert "refresh-secret" not in stored.refresh_token
            assert account.oauth_state == "state-secret"
            assert account.access_token == "access-secret"
            assert account.refresh_token == "refresh-secret"
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        get_settings.cache_clear()
