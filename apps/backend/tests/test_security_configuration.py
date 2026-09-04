import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import app.main as app_main
from app.core.config import Settings


def production_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": "production",
        "debug": False,
        "frontend_origin": "https://app.creator.test",
        "trusted_hosts": "api.creator.test",
        "session_cookie_secure": True,
        "database_url": "postgresql+psycopg://user:private@db/creatoros",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"debug": True}, "DEBUG must be false in production"),
        (
            {"session_cookie_secure": False},
            "SESSION_COOKIE_SECURE must be true in production",
        ),
        (
            {"frontend_origin": "http://app.creator.test"},
            "FRONTEND_ORIGIN must use HTTPS in production",
        ),
        (
            {"trusted_hosts": "*"},
            "TRUSTED_HOSTS cannot contain a wildcard in production",
        ),
    ],
)
def test_production_settings_fail_closed(
    override: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        production_settings(**override)


def test_frontend_origin_rejects_credentials_and_paths() -> None:
    with pytest.raises(ValidationError, match="must be an HTTP\\(S\\) origin"):
        Settings(
            _env_file=None,
            frontend_origin="https://user:password@app.creator.test/path",
        )


def test_database_url_is_redacted_by_settings() -> None:
    settings = production_settings()

    assert "private" not in repr(settings)
    assert settings.database_url.get_secret_value().endswith("@db/creatoros")


def test_production_application_hardening(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = production_settings()
    monkeypatch.setattr(app_main, "get_settings", lambda: settings)
    application = app_main.create_application()

    with TestClient(
        application,
        base_url="https://api.creator.test",
    ) as client:
        response = client.get("/")
        docs_response = client.get("/docs")
        rejected_host = client.get("/", headers={"Host": "untrusted.test"})

    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["content-security-policy"].startswith("default-src 'none'")
    assert docs_response.status_code == 404
    assert rejected_host.status_code == 400


def test_cors_allows_only_configured_origin_and_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(_env_file=None)
    monkeypatch.setattr(app_main, "get_settings", lambda: settings)
    application = app_main.create_application()

    with TestClient(application) as client:
        allowed = client.options(
            "/api/health",
            headers={
                "Origin": settings.frontend_origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": (
                    "Content-Type,Idempotency-Key,X-CSRF-Token,X-Workspace-ID"
                ),
            },
        )
        rejected = client.options(
            "/api/health",
            headers={
                "Origin": "https://untrusted.test",
                "Access-Control-Request-Method": "POST",
            },
        )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == settings.frontend_origin
    assert rejected.headers.get("access-control-allow-origin") is None
