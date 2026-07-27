from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.db.init_db import check_database_connection
from app.db.session import get_db
from app.main import app


class FakeSession:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.executed_statement = ""

    def execute(self, statement: object) -> None:
        self.executed_statement = str(statement)
        if self.error is not None:
            raise self.error


def test_root_endpoint(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"message": "CreatorOS Brain is online \U0001f9e0"}


def test_application_health_endpoint(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "CreatorOS API"}


def test_database_connection_check_executes_lightweight_query() -> None:
    session = FakeSession()

    check_database_connection(session)  # type: ignore[arg-type]

    assert session.executed_statement == "SELECT 1"


def test_database_health_endpoint_reports_reachable(client: TestClient) -> None:
    session = FakeSession()
    app.dependency_overrides[get_db] = lambda: session

    response = client.get("/api/health/database")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "reachable"}
    assert session.executed_statement == "SELECT 1"


def test_database_health_endpoint_hides_error_details(client: TestClient) -> None:
    session = FakeSession(SQLAlchemyError("private connection detail"))
    app.dependency_overrides[get_db] = lambda: session

    response = client.get("/api/health/database")

    assert response.status_code == 503
    assert response.json() == {"detail": "Database is unavailable"}
    assert "private connection detail" not in response.text
