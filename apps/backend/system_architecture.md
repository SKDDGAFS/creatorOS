# CreatorOS backend architecture

## Application boundary

- `app/main.py` owns the FastAPI application factory, middleware, and root route.
- `app/api/router.py` owns the `/api` prefix and composes feature routers.
- `app/api/routes/health.py` owns application and database readiness checks.
- Root-level `main.py` is a compatibility entry point for `uvicorn main:app`.
- The frontend and `docker-compose.yml` are outside this sprint's change boundary.

## Configuration

`app/core/config.py` loads these environment variables with Pydantic Settings:

- `APPLICATION_NAME`
- `ENVIRONMENT`
- `DEBUG`
- `DATABASE_URL`
- `FRONTEND_ORIGIN`

The safe template is `.env.example`. A real `.env` remains local and must not be
committed. The expected local URL format is:

```text
postgresql+psycopg://creatoros:creatoros_password@localhost:5432/creatoros
```

## Database access

- SQLAlchemy 2.x uses a synchronous engine and `Session`.
- `get_db()` supplies one request-scoped session and always closes it.
- `pool_pre_ping=True` detects stale pooled connections.
- `init_db.py` contains only a read-only connectivity query. It never calls
  `Base.metadata.create_all()`.

## Domain model

- All four domain models use UUID primary keys. UUIDs allow future ingestion and
  distributed workflows to create identifiers without coordinating an integer
  sequence.
- All timestamps are timezone-aware and generated in UTC.
- Channel platforms and video statuses are stored as strings. Python enums define
  the application vocabulary, while named database `CHECK` constraints enforce it.
- `Video.platform_video_id` is nullable. PostgreSQL permits multiple null values
  under its channel/video unique constraint.
- Video metrics are appendable snapshots. The `(video_id, captured_at)` index
  supports historical time-series queries.

## Data retention

- Foreign keys use `ON DELETE RESTRICT`.
- Relationships use explicit `back_populates`.
- ORM relationships do not enable `delete` or `delete-orphan` cascades.
- Parent deletion therefore fails while dependent records exist; cleanup must be
  an explicit, reviewed operation.

## Schema changes

Alembic is the schema source of truth. The initial revision is:

```text
alembic/versions/0001_initial_models.py
```

Create future revisions after changing model metadata:

```powershell
.\venv\Scripts\alembic.exe revision --autogenerate -m "describe change"
```

Review every generated migration before applying it:

```powershell
.\venv\Scripts\alembic.exe upgrade head
```

## Local commands

Install dependencies:

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

Run the server:

```powershell
.\venv\Scripts\uvicorn.exe main:app --reload
```

Run tests:

```powershell
.\venv\Scripts\python.exe -m pytest -q
```

Generate migration SQL without changing the database:

```powershell
.\venv\Scripts\alembic.exe upgrade head --sql
```

## Sprint 2 API boundary

- `app/api/routes/channels.py` owns channel HTTP input, output, pagination,
  filtering, and status codes.
- `app/api/routes/videos.py` owns video and metric HTTP behavior.
- `app/services/channel_service.py` and `app/services/video_service.py` own
  business rules, SQLAlchemy queries, transactions, parent checks, and partial
  updates.
- `app/api/errors.py` converts safe service exceptions into stable HTTP `404`,
  `409`, and generic `500` responses.
- Pydantic schemas reject unsupported enum values, nulls for required update
  fields, naive publishing timestamps, negative metrics, and click-through rates
  outside the decimal ratio range of 0 through 1.

All list endpoints use bounded `limit`/`offset` pagination and deterministic
timestamp-plus-UUID ordering. Channel lists can filter by user, platform, and
active state. Video lists can filter by channel and status.

Metric snapshots are append-only. Their read endpoint supports `newest` and
`oldest` ordering. Revision `0002` adds database checks matching the Pydantic
metric rules, so non-API writes cannot store negative counts or invalid rates.

API examples and the complete route list are documented in `API.md`.
