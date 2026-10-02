# CreatorOS backend architecture

## Application boundary

- `app/main.py` owns the FastAPI application factory, middleware, and root route.
- `app/api/router.py` owns the `/api` prefix and composes feature routers.
- `app/api/routes/health.py` owns application and database readiness checks.
- Root-level `main.py` is a compatibility entry point for `uvicorn main:app`.
- The frontend has Home, Schedule, Content, Connections, and Settings routes.
  Content reads the paginated Video API. Future features are explicitly marked
  as unavailable; there is no authentication UI or analytics dashboard.

## Configuration

`app/core/config.py` loads these environment variables with Pydantic Settings:

- `APPLICATION_NAME`
- `ENVIRONMENT`
- `DEBUG`
- `DATABASE_URL`
- `FRONTEND_ORIGIN`
- `CREDENTIAL_ENCRYPTION_KEY`
- `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, and `WHISPER_MODEL`

The safe template is `.env.example`. A real `.env` remains local and must not be
committed. The expected local URL format is:

```text
postgresql+psycopg://creatoros:creatoros_password@127.0.0.1:5432/creatoros
```

## Database access

- SQLAlchemy 2.x uses a synchronous engine and `Session`.
- `get_db()` supplies one request-scoped session and always closes it.
- `pool_pre_ping=True` detects stale pooled connections.
- `init_db.py` contains only a read-only connectivity query. It never calls
  `Base.metadata.create_all()`.

## Domain model

CreatorOS is a private, single-user content preparation and scheduling
assistant. `Channel` remains a local preparation target. `Account` is a separate
connected-platform identity with OAuth state, scopes, tokens, and connection
status. There is no local sign-in requirement; OAuth authorizes a platform
account, not access to CreatorOS.

OAuth state and access/refresh tokens use an authenticated Fernet
`TypeDecorator`; the database contains ciphertext, while ORM access decrypts
inside the backend. A local `CREDENTIAL_ENCRYPTION_KEY` must be generated before
credentials are written. It is not exposed by any response schema. Keep a
separate backup of the key; key rotation requires an explicit re-encryption
operation. No account connection endpoints or platform SDK calls are enabled
yet.

- All five domain models use UUID primary keys. UUIDs allow future ingestion and
  distributed workflows to create identifiers without coordinating an integer
  sequence.
- Account records are independent of local channels. A platform account can be
  connected later without reclassifying the existing preparation targets.
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

## Repository hardening controls

- Docker publishes the development PostgreSQL port on `127.0.0.1` only. The
  Compose credential is a local default and is not suitable for shared or
  production environments.
- `requirements.txt` states supported direct dependency ranges.
  `requirements.lock` records the exact tested environment, while
  `requirements-dev.txt` adds pinned lint, type-check, and audit tools.
- Ruff checks Python correctness, imports, and common bug patterns. Mypy checks
  application and migration type contracts. Tests remain isolated from the local
  database.
- CI runs unit tests and static checks, applies Alembic migrations to a disposable
  PostgreSQL 16 service, and audits Python dependencies.
- Dashboard CI uses a clean npm install, Biome, TypeScript, a production Next.js
  build, and an npm audit.
- Dependabot proposes weekly Python and npm dependency updates. GitHub secret
  scanning and push protection remain repository settings.

The dashboard API origin is read from `NEXT_PUBLIC_API_URL`. Because values with
the `NEXT_PUBLIC_` prefix are included in browser code, this variable must never
contain a credential.

Public deployment remains blocked until authentication, record-level
authorization, request limits, production CORS, secret management, and operational
monitoring are implemented and reviewed.

## Analytics semantic debt

The current metric schema treats omitted numeric values as zero. Analytics work
must first define which platform fields can be unavailable and migrate those
fields to nullable storage where needed. A genuine zero must remain distinct from
missing or unsupported platform data. Click-through rate is currently stored as
a decimal ratio; future ingestion must record whether it was platform-reported or
derived.

## Scheduling direction

Performance data is an internal input for scheduling. Existing VideoMetric
snapshots, publication timestamps, channel references, indexes, and metric APIs
remain intact. There is no recommendation algorithm or publisher in this sprint.

The intended flow is frontend → FastAPI → PostgreSQL content/channel history →
internal performance analysis → posting-time recommendation → user approval →
platform publisher. Only the content/channel/history portion exists today.

No new model or migration is needed for the current read-only foundation.
`docs/SCHEDULING.md` at the repository root defines the smallest proposed queue
record and future recommendation and metadata service contracts. A Video status
of `scheduled` is historical data, not an executable publishing job.

## Local AI and platform boundaries

- `app/providers/ai/base.py` defines the provider contract for transcription,
  analysis, metadata, topic ideation, and recommendation.
- `OllamaProvider` sends text prompts only to the configured local Ollama URL.
  `FasterWhisperTranscriber` is optional and loads its model locally. Topic
  ideation is labeled unverified; sparse scheduling history returns unavailable.
- `POST /api/videos/{video_id}/prepare` stores transcript, analysis, and
  platform-specific metadata drafts on the existing local Video record.
  Publishing is not invoked. Content provides the review and edit step.
- `app/platforms/base.py` defines the common platform adapter contract. YouTube,
  Instagram, and TikTok OAuth/publishing adapters remain future integrations;
  platform app review, account eligibility, scopes, and credentials are
  prerequisites, especially for TikTok and Instagram.
