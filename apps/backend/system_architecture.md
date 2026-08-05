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
- `SESSION_COOKIE_NAME`
- `CSRF_COOKIE_NAME`
- `SESSION_COOKIE_SECURE`
- authentication expiry and login throttle settings

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

## Authentication and ownership

- Passwords use `pwdlib`'s recommended Argon2id hash. Plaintext passwords are
  never stored.
- Login creates an opaque random session token and a separate CSRF token. Only
  their SHA-256 hashes are persisted.
- Authentication is carried by an HTTP-only, `SameSite=Lax` cookie. Authenticated
  writes require a matching CSRF cookie/header pair bound to the session.
- Login throttles are persisted by a one-way hash of the normalized email, so
  throttling works across application workers without storing the identifier.
- Every user receives a personal workspace and owner membership. Workspace roles
  are owner, admin, member, and viewer.
- Channel ownership is derived server-side from the session and active workspace.
  Videos and metrics inherit authorization through their channel.
- Revision `0003` disables legacy passwordless users, backfills personal
  workspaces, and adds the authentication tables.

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
- Shared analytics fields are nullable. A null means unavailable or unsupported;
  zero remains a genuine reported zero.
- Retention points, traffic sources, demographics, geography, and discovery
  assets are normalized child records owned by one metric snapshot.
- TikTok, Instagram, and YouTube extensions are one-to-one snapshot records.
  The service rejects extensions that do not match the channel platform.
- Rates are derived only from complete inputs with a nonzero denominator.
  Derived values are returned by the API and not stored.

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
timestamp-plus-UUID ordering. Channel lists can filter by platform and active
state. Video lists can filter by channel and status. Every query is scoped to
the active workspace.

Metric snapshots are append-only. Their read endpoint supports `newest` and
`oldest` ordering. Revision `0002` adds database checks matching the Pydantic
metric rules, so non-API writes cannot store negative counts or invalid rates.
Revision `0004` expands nullable analytics, video duration, structured breakdowns,
and platform extensions with named checks and restrictive foreign keys.

## Growth-signal configuration

- `GrowthSignalProfile` is workspace-owned and immutable except for deactivation.
  Recreating a name allocates a new version for reproducible historical scoring.
- Profile context includes platform, content format, account-size range,
  video-duration range, goal, and evidence-volume range.
- `GrowthSignalWeight` stores user-configured weight, advisory tier, minimum
  sample size, and full-confidence sample size. No universal numerical weight is
  hardcoded.
- Scoring combines normalized observations with sample-size and source
  confidence. It returns score, confidence, coverage, and auditable individual
  contributions.
- Missing observations reduce coverage. Insufficient samples contribute no
  confidence. Interpretations explicitly describe associations as directional or
  correlational rather than causal.
- Revision `0005` adds the profile and weight tables.

API examples and the complete route list are documented in `API.md`.

## Publishing workflow

- `PublishingJob` is workspace-owned, linked to a workspace-visible video, and
  created with a hashed idempotency key.
- `publishing_service.ALLOWED_TRANSITIONS` is the single state graph. HTTP routes
  expose named actions instead of a general status update.
- `ApprovalRequest` records each review round and the requesting and deciding
  users. Only workspace owners and administrators can approve or reject.
- A job cannot be scheduled or enter worker publishing without an approved human
  decision.
- `PublishingTransition` is immutable workflow history. `ActivityEvent` supplies
  the workspace activity feed with safe structured metadata.
- State, approval, transition, and activity writes commit atomically. Errors roll
  back the entire action.
- Rejected and failed jobs may retry through preparation. Published and cancelled
  jobs are terminal.
- Worker-only service methods can record start, safe failure, and confirmed
  success. No route or service in this sprint contacts an external platform.
- Revision `0006` adds the publishing, approval, transition, and activity tables
  with restrictive foreign keys.

## Durable job system

- `DurableJob` stores workspace ownership, a typed JSON payload, priority,
  schedule, attempt budget, idempotency hash, lease, safe errors, result, and
  lifecycle timestamps.
- `JobAttempt` preserves every execution attempt, including abandoned stale
  leases. Jobs and attempts use restrictive foreign keys and no destructive ORM
  cascades.
- Workers claim eligible rows with `SELECT ... FOR UPDATE SKIP LOCKED`, commit
  the lease, and only then execute a handler. Handler execution therefore never
  holds a database transaction open.
- Lease ownership is checked before heartbeat, completion, or failure.
  Cancellation clears the lease, so a cancelled worker cannot record success.
- Retryable failures use capped exponential backoff. Stale-lock recovery either
  reschedules within the attempt budget or records a final failure.
- Enqueueing can be idempotent per workspace and job type. Only a hash of the
  opaque key is stored.
- `JobRegistry` maps validated job types to typed Python callables. Unexpected
  exceptions are converted to a generic safe error and never expose exception
  text.
- Generic enqueueing is internal rather than an API route. HTTP exposes
  workspace observability and administrator cancellation only.
- PostgreSQL is the queue; Redis and Celery are not required at the current
  scale. Revision `0007` adds the job and attempt tables.

## Platform adapter framework

- `PlatformAdapter` is the provider-neutral protocol for account lifecycle,
  channel/video/metric synchronization, publish validation, idempotent
  publishing, status polling, and revocation.
- DTOs use strict Pydantic models. Credentials are `SecretStr` values and metric
  snapshots distinguish unavailable fields from reported zeros.
- `CredentialStore` is the only at-rest secret boundary. Connection rows contain
  a reference returned by that store, never access tokens, refresh tokens,
  authorization codes, client secrets, or PKCE verifiers.
- `PlatformAdapterRegistry` permits one typed adapter per platform. Sprints H
  through J supply the official YouTube, Instagram, and TikTok implementations.
- `PlatformSyncCursor` persists opaque pagination state by connection and
  resource type.
- `PlatformOperation` binds a hashed idempotency key to a canonical request
  fingerprint and provider resource ID, preventing silent key reuse.
- `PlatformRequestLog` stores no query string or response body. Headers, request
  bodies, and Pydantic models are recursively redacted before persistence.
- Adapter errors classify authentication/expiry, rate limits, transient
  failures, permanent failures, and unsupported capabilities for job retry
  policy.
- Revision `0008` adds workspace-owned connections, cursors, operations, and
  redacted request logs with restrictive foreign keys.

## YouTube integration

- `platforms/youtube/oauth.py` creates random state and PKCE material. Only the
  state hash and secret-store reference enter PostgreSQL. The state is bound to
  one workspace/user, row-locked during callback, expires quickly, and is
  consumed before a provider exchange.
- `YouTubeHttpTransport` is the only Google HTTP boundary. It uses current
  official REST endpoints, fixed HTTPS origins, bounded timeouts, bearer
  headers, classified safe errors, quota callbacks, and query/body-free request
  telemetry. Resumable upload locations are restricted to approved Google
  hosts, preventing a provider response from becoming an SSRF primitive.
- `YouTubeAdapter` maps provider resources into provider-neutral DTOs. It
  discovers the uploads playlist, batches at most 50 video IDs, preserves
  unavailable analytics, and separates validation from upload dispatch.
- `youtube_service` owns credential refresh, connection/reconnection,
  workspace-scoped local upserts, cursor persistence, append-only metric
  snapshots, telemetry flushing, revocation, and credential deletion. Routes
  contain authorization/dependency wiring only.
- Access and refresh tokens remain behind `PlatformSecretStore`. The included
  in-memory implementation is development/test only and production refuses it.
- `OAuthAuthorizationState` and `PlatformQuotaUsage` were added by revision
  `0009`. The same revision removes the incorrect upper bound on absolute
  audience-retention ratio because YouTube documents valid rewatch values above
  `1`.
- Targeted Analytics queries provide activity, retention, traffic-source, and
  subscribed-status data. The newer thumbnail reach reports belong to the bulk
  Reporting API, so the targeted adapter leaves reported impressions CTR null
  rather than inventing or mislabeling it.
- Application publishing remains unavailable until the authorized media-store
  boundary exists. The transport and adapter can be fully tested through an
  injected media source without opening local paths or contacting Google.

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

Public deployment remains blocked until general request limits, production CORS,
trusted hosts, secret management, TLS/network controls, and operational
monitoring are implemented and reviewed.

## Analytics semantics

Metric inputs retain source meaning: unavailable fields are null, reported zeros
remain zero, and click-through rates use decimal ratios. The shared
`click_through_rate` can represent a normalized source value; YouTube's explicitly
reported impressions CTR is retained separately in its extension. Future
platform adapters must map official source fields without filling unsupported
measurements.

## Instagram integration

- `platforms/instagram/oauth.py` implements Instagram Login state creation and
  one-time callback claiming. It requests basic and insights scopes by default
  and gates the content-publishing scope behind explicit configuration.
- `InstagramHttpTransport` is the only Meta HTTP boundary. It uses fixed
  Instagram origins, a configurable versioned Graph path, bearer headers,
  bounded timeouts, safe Meta error classification, request telemetry, and
  per-bucket usage accounting.
- `InstagramAdapter` maps one professional account to a channel, paginated owned
  media to videos, media insights to append-only video metrics, and daily
  account insights to provider-neutral account snapshots.
- `PlatformAccountMetricSnapshot` stores append-only connection-level insight
  values, unavailable-field names, period, and safe provider metadata. Revision
  `0010` adds the table with a restrictive connection foreign key.
- Total reach maps to `accounts_reached`. Current targeted endpoints do not
  expose dependable Reels-tab, Feed, Explore, or profile reach breakdowns, so
  those fields stay null.
- The adapter validates public HTTPS media references, creates official
  publishing containers, checks their state, finalizes ready containers, and
  reads the rolling publishing limit. Runtime dispatch remains disabled until
  the media-storage and publishing-worker sprints.
- Disconnect revokes Meta permissions, marks the SQL connection disconnected,
  and removes the secret-store reference. Provider messages and response bodies
  never enter persisted telemetry.

## TikTok integration

- `platforms/tiktok/oauth.py` creates a one-time, user/workspace-bound OAuth
  state for Login Kit v2 and gates `video.publish` behind explicit settings.
- `TikTokHttpTransport` owns all TikTok HTTP behavior: token lifecycle, profile,
  Display API video pages, creator-information validation, direct-post
  initialization/status contracts, quota callbacks, and redacted telemetry.
- `TikTokAdapter` maps profile and video resources into provider-neutral DTOs.
  Display API counters map to reported metric fields; unavailable traffic,
  retention, impression, and click-through analytics remain null.
- `tiktok_service` owns credential refresh, safe connection replacement,
  workspace-scoped upserts, opaque cursor persistence, append-only account and
  video snapshots, telemetry flushing, revocation, and secret deletion.
- The implementation reuses revision `0010` tables, including
  `TikTokMetricExtension`; Sprint J requires no schema migration.
- Direct-post validation queries current creator restrictions and requires an
  explicit privacy choice. Runtime media dispatch remains disabled until the
  authorized media-store boundary is implemented. Tests inject a fake transport
  and never contact TikTok.
