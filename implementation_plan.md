# CreatorOS Backend Foundation Sprint

## Current state

- `apps/backend/main.py` contains the working FastAPI application, CORS middleware, and root endpoint.
- `apps/backend/docker-compose.yml` runs PostgreSQL 16 with a persistent volume.
- No existing database layer, models, migrations, dependency manifest, or backend tests were found.
- No backend-specific `AGENTS.md`, `system_architecture.md`, or `.cursorrules` file exists.

## Implementation choices

- Use synchronous SQLAlchemy 2.x with Psycopg 3.
- Use UUID primary keys consistently for user-owned, externally referenced domain records.
- Use PostgreSQL enum types for channel platform and video status.
- Keep ORM cascades non-destructive: relationships use `save-update, merge`; foreign keys default to `RESTRICT`. Historical data is not deleted implicitly.
- Use Alembic as the production schema mechanism. `init_db.py` will only provide a connection check and will not call `create_all()`.
- Make database health independently testable through dependency injection, so tests do not touch the developer database.

## Planned files

### Application structure

- `[NEW] apps/backend/app/__init__.py`
- `[NEW] apps/backend/app/main.py` — application factory, root route, configured CORS, API router registration.
- `[NEW] apps/backend/app/api/__init__.py`
- `[NEW] apps/backend/app/api/router.py` — central `/api` router.
- `[NEW] apps/backend/app/api/routes/__init__.py`
- `[NEW] apps/backend/app/api/routes/health.py` — application and database health endpoints.
- `[NEW] apps/backend/app/core/__init__.py`
- `[NEW] apps/backend/app/core/config.py` — cached Pydantic Settings configuration.
- `[NEW] apps/backend/app/db/__init__.py`
- `[NEW] apps/backend/app/db/base.py` — SQLAlchemy declarative base and model metadata imports.
- `[NEW] apps/backend/app/db/session.py` — engine, session factory, and request-scoped session dependency.
- `[NEW] apps/backend/app/db/init_db.py` — lightweight database connectivity check.
- `[NEW] apps/backend/app/models/__init__.py`
- `[NEW] apps/backend/app/models/user.py`
- `[NEW] apps/backend/app/models/channel.py`
- `[NEW] apps/backend/app/models/video.py`
- `[NEW] apps/backend/app/models/video_metric.py`
- `[NEW] apps/backend/app/schemas/__init__.py`
- `[NEW] apps/backend/app/services/__init__.py`
- `[MODIFY] apps/backend/main.py` — compatibility shim exporting the restructured app so existing `uvicorn main:app` usage continues to work.

### Database and migrations

- `[NEW] apps/backend/alembic.ini`
- `[NEW] apps/backend/alembic/env.py`
- `[NEW] apps/backend/alembic/script.py.mako`
- `[NEW] apps/backend/alembic/versions/0001_initial_models.py` — initial schema for users, channels, videos, and video metrics with constraints and indexes.
- `[NEW] apps/backend/alembic/versions/__init__.py`
- `[NEW] apps/backend/alembic/__init__.py`

### Configuration and dependencies

- `[NEW] apps/backend/.env.example` — safe local configuration template, including the exact Psycopg URL format.
- `[NEW] apps/backend/requirements.txt` — FastAPI, Uvicorn, SQLAlchemy 2.x, Psycopg, Alembic, Pydantic Settings, and Pytest dependencies.
- `[MODIFY] apps/backend/docker-compose.yml` — load non-secret local defaults through environment variables while preserving the existing container, port, database, and volume behavior.

### Tests

- `[NEW] apps/backend/tests/__init__.py`
- `[NEW] apps/backend/tests/conftest.py`
- `[NEW] apps/backend/tests/test_health.py` — root, application health, successful database health, and unavailable database health without using PostgreSQL.
- `[NEW] apps/backend/tests/test_models.py` — model tables, relationships, unique constraints, enum-backed columns, foreign keys, and metric time-query index.

### Documentation/state

- `[NEW] apps/backend/system_architecture.md` — backend boundaries, migration policy, ID strategy, deletion policy, configuration, and run commands.
- `[NEW] apps/backend/task.md` — execution checklist updated as implementation and verification complete.

## Verification

1. Install or validate Python dependencies in an isolated backend virtual environment if available.
2. Run `pytest`.
3. Run Alembic offline SQL generation to verify migration configuration without changing the developer database.
4. Import the FastAPI application and validate route registration.
5. Report any checks that cannot run because dependencies or local services are unavailable.

## Out of scope

- Authentication
- AI agents
- Publishing integrations
- Analytics ingestion
- Frontend changes or redesign
