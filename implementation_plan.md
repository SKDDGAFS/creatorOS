# CreatorOS Backend Foundation Sprint

## Current state

- `apps/backend/main.py` contains the working FastAPI application, CORS middleware, and root endpoint.
- `apps/backend/docker-compose.yml` runs PostgreSQL 16 with a persistent volume.
- No existing database layer, models, migrations, dependency manifest, or backend tests were found.
- No backend-specific `AGENTS.md`, `system_architecture.md`, or `.cursorrules` file exists.

## Implementation choices

- Use synchronous SQLAlchemy 2.x with Psycopg 3.
- Use UUID primary keys consistently for user-owned, externally referenced domain records.
- Store channel platform and video status as strings with application enums and
  named database `CHECK` constraints.
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

---

# CreatorOS Backend Sprint 2: Core Channel and Video APIs

## Scope

- `[NEW] apps/backend/app/services/errors.py` — domain-safe service exceptions.
- `[NEW] apps/backend/app/services/channel_service.py` — channel create, list, get, and partial update operations.
- `[NEW] apps/backend/app/services/video_service.py` — video CRUD and append-only metric operations.
- `[NEW] apps/backend/app/api/errors.py` — translates service errors into stable HTTP responses.
- `[NEW] apps/backend/app/api/routes/channels.py` — channel HTTP endpoints, filters, and pagination.
- `[NEW] apps/backend/app/api/routes/videos.py` — video and metric HTTP endpoints, filters, ordering, and pagination.
- `[MODIFY] apps/backend/app/api/router.py` — register the new routers.
- `[MODIFY] apps/backend/app/models/video_metric.py` — add database checks for non-negative metrics and a 0–1 click-through-rate convention.
- `[NEW] apps/backend/alembic/versions/0002_metric_value_constraints.py` — apply the metric checks through Alembic.
- `[MODIFY] apps/backend/tests/conftest.py` — isolate API tests in an in-memory SQLite database.
- `[NEW] apps/backend/tests/test_core_apis.py` — cover success, validation, conflicts, filtering, pagination, and ordering.
- `[NEW] apps/backend/API.md` — endpoint and request/response documentation.
- `[MODIFY] apps/backend/system_architecture.md` — record Sprint 2 service and API conventions.
- `[MODIFY] apps/backend/task.md` — track implementation and verification.

## Decisions

- Routes own HTTP status codes and query validation.
- Services own database queries, parent validation, partial-update behavior, and transaction handling.
- Service exceptions contain safe messages and are translated into `404`, `409`, or generic `500` responses.
- List endpoints use `limit` and `offset`, cap `limit` at 100, and apply deterministic ordering.
- Click-through rate is stored as a decimal ratio from 0 through 1 (`0.05` means 5%).
- Metric history is append-only and can be read newest-first or oldest-first.
- Test-only `Base.metadata.create_all()` is allowed for isolated SQLite tests; Alembic remains the production schema source of truth.

## Verification

1. Import the application and inspect registered routes.
2. Run the complete Pytest suite.
3. Generate Alembic SQL through revision `0002` without modifying PostgreSQL.
4. Confirm the working tree only contains Sprint 2 backend files.

---

# CreatorOS Repository Hardening Sprint

## Goal

Make the current local-development foundation safer and reproducible before
adding analytics or publishing behavior.

## Scope

- Bind the development PostgreSQL port to localhost only.
- Move the dashboard API origin into a documented public environment variable.
- Repair dashboard encoding and metadata.
- Add reproducible Python development dependencies and static checks.
- Upgrade and audit dashboard dependencies without using unsafe forced fixes.
- Add continuous integration and Dependabot configuration.
- Add security, setup, rollback, and deployment-boundary documentation.

## Safety boundaries

- Do not change database tables or apply migrations.
- Do not rotate the existing local PostgreSQL password automatically because the
  persistent volume was initialized with the current credential.
- Do not add authentication, analytics schema changes, or publishing behavior.
- Do not recommend a public deployment while authentication and request controls
  remain absent.
- Do not merge while critical or high dependency findings remain unresolved.

## Verification

1. Run backend tests, Ruff, mypy, pip check, and pip-audit.
2. Run dashboard lint, TypeScript, production build, and npm audit.
3. Validate Docker Compose and Alembic state without changing the database.
4. Inspect the final diff, ignored secrets, and repository status.
5. Complete the sprint review gate and report remaining risks.

---

# CreatorOS Sprint B: Authentication and Ownership

## Goal

Replace client-supplied ownership with authenticated, workspace-scoped access
while preserving existing channel, video, and metric data.

## Security design

- Hash passwords with Argon2id through `pwdlib`.
- Store only SHA-256 hashes of cryptographically random session and reset tokens.
- Send the session identifier only in an HTTP-only, same-site cookie.
- Bind a separate CSRF token to each server-side session and require it on
  authenticated state-changing requests.
- Apply generic login failures and database-backed throttling.
- Require active users and unexpired, non-revoked sessions.
- Resolve ownership through workspace membership, never request `user_id`.

## Planned files

### Configuration and security

- `[MODIFY] apps/backend/app/core/config.py`
- `[NEW] apps/backend/app/core/security.py`
- `[MODIFY] apps/backend/.env.example`
- `[MODIFY] apps/backend/requirements.txt`
- `[MODIFY] apps/backend/requirements.lock`

### Models and migration

- `[MODIFY] apps/backend/app/models/user.py`
- `[MODIFY] apps/backend/app/models/channel.py`
- `[NEW] apps/backend/app/models/workspace.py`
- `[NEW] apps/backend/app/models/auth_session.py`
- `[NEW] apps/backend/app/models/auth_throttle.py`
- `[NEW] apps/backend/app/models/password_reset_token.py`
- `[MODIFY] apps/backend/app/models/__init__.py`
- `[NEW] apps/backend/alembic/versions/0003_authentication_and_ownership.py`

The migration will create a personal workspace and owner membership for every
existing user, attach existing channels to those workspaces, and mark legacy
users inactive because they do not have passwords.

### Schemas, services, and dependencies

- `[NEW] apps/backend/app/schemas/auth.py`
- `[NEW] apps/backend/app/schemas/workspace.py`
- `[MODIFY] apps/backend/app/schemas/channel.py`
- `[NEW] apps/backend/app/services/auth_service.py`
- `[NEW] apps/backend/app/services/workspace_service.py`
- `[MODIFY] apps/backend/app/services/channel_service.py`
- `[MODIFY] apps/backend/app/services/video_service.py`
- `[MODIFY] apps/backend/app/services/errors.py`
- `[NEW] apps/backend/app/api/dependencies/auth.py`

### Routes

- `[NEW] apps/backend/app/api/routes/auth.py`
- `[NEW] apps/backend/app/api/routes/workspaces.py`
- `[MODIFY] apps/backend/app/api/routes/channels.py`
- `[MODIFY] apps/backend/app/api/routes/videos.py`
- `[MODIFY] apps/backend/app/api/router.py`

### Tests and documentation

- `[MODIFY] apps/backend/tests/conftest.py`
- `[NEW] apps/backend/tests/test_auth.py`
- `[NEW] apps/backend/tests/test_authorization.py`
- `[MODIFY] apps/backend/tests/test_core_apis.py`
- `[MODIFY] apps/backend/tests/test_models.py`
- `[MODIFY] apps/backend/API.md`
- `[MODIFY] apps/backend/system_architecture.md`
- `[MODIFY] README.md`

## Verification

1. Test registration, login, logout, session expiry, CSRF, throttling, disabled
   accounts, workspaces, roles, and cross-workspace access denial.
2. Run Ruff, mypy, Pytest, and pip-audit.
3. Review migration SQL before applying revision `0003`.
4. Apply `0003` only to the confirmed local development database.
5. Run Alembic current, drift, and offline SQL checks.
6. Review secrets, staged files, and the complete diff.

## Out of scope

- Email delivery for password resets.
- OAuth or social-platform credentials.
- Public deployment.
- Automatic pull-request merging.

# Sprint C implementation plan: analytics schema expansion

## Scope

1. Change shared snapshot measurements to nullable values so unavailable data is
   not stored as a fabricated zero.
2. Add shared reach, engagement, follower, audience, completion, and first-hour
   measurements without duplicating existing fields.
3. Compute rates from complete source measurements at response time; return null
   when a denominator or required source value is unavailable.
4. Store retention points, traffic sources, demographics, geography, and
   discovery assets in typed child records.
5. Add one-to-one TikTok, Instagram, and YouTube metric extensions and reject an
   extension that does not match the video's channel platform.
6. Preserve append-only snapshots and workspace authorization.

## Data rules

- Counts and durations are nullable and non-negative when supplied.
- Ratios use decimal storage and must be between zero and one.
- A video duration is optional and positive when supplied.
- Child records use restrictive foreign keys, named uniqueness constraints, and
  no destructive ORM cascades.
- Derived rates are absent rather than misleading when inputs are incomplete.
- Revision `0004` is forward-only during this sprint and must be reviewed in
  offline SQL before local application.

## Verification

1. Test nullable semantics, each structured child type, platform matching,
   derived rates, constraints, append-only history, and workspace isolation.
2. Run Ruff, mypy, Pytest, pip-audit, Alembic current/drift/offline SQL, secret
   scanning, and diff checks.
3. Update API and architecture documentation.
4. Commit, push, and open a draft pull request stacked on Sprint B.

# Sprint D implementation plan: growth-signal configuration

## Scope

1. Add workspace-owned, versionable signal profiles scoped by platform, content
   format, account-size range, video-length range, goal, and evidence volume.
2. Add configurable positive weights for the roadmap signal catalog; strength
   tiers are descriptive metadata and never determine permanent weights.
3. Add minimum and full-confidence sample sizes per signal.
4. Score normalized observations with source confidence, sample-size confidence,
   evidence coverage, and explicit per-signal contributions.
5. Keep profiles immutable after creation so historical scores remain
   reproducible; new strategies use a new named/versioned profile.

## Safety and verification

- Profiles and all reads/scores are workspace isolated.
- Every constraint and foreign key is named and restrictive.
- Scores remain between zero and one and never imply causal certainty.
- Review migration `0005` SQL before local application.
- Add service, API, authorization, scoring, constraint, and edge-case tests.

# Sprint E implementation plan: publishing workflow

## Scope

1. Add workspace-owned publishing jobs linked to workspace-owned videos.
2. Enforce the roadmap states through one centralized transition graph; no route
   accepts arbitrary status updates.
3. Require a pending human approval before scheduling or publishing.
4. Add approval decisions, schedules, cancellations, safe failures, retries,
   immutable transition history, and activity events.
5. Make job creation idempotent per workspace through an opaque
   `Idempotency-Key` request header.
6. Keep every state change and its audit/activity records in one database
   transaction.

## Boundaries

- This sprint records workflow intent only and never calls a social platform.
- Worker-only publishing transitions remain service methods until the durable job
  and adapter sprints.
- Published content cannot be deleted through this workflow.
- Review migration `0006` SQL before local application.

# Sprint F implementation plan: durable job system

## Scope

1. Add workspace-owned durable jobs and immutable per-attempt history.
2. Store typed payloads, priority, schedule, attempt limits, leases, safe errors,
   results, and lifecycle timestamps in PostgreSQL.
3. Claim eligible work with row locking and `SKIP LOCKED`; never hold a database
   transaction open while a handler runs.
4. Add exponential retry backoff, heartbeat-based lease extension, stale-lock
   recovery, cancellation, and idempotent enqueueing.
5. Add a typed in-process handler registry and single-job runner without shell
   execution or an additional infrastructure dependency.
6. Expose workspace-scoped job observability and administrator cancellation, but
   do not expose generic job enqueueing to HTTP clients.

## Safety and verification

- Payloads must be JSON objects and must never contain credentials or secrets.
- Lock ownership is verified before completion, failure, or heartbeat.
- Terminal jobs cannot be mutated, and cancellation invalidates active leases.
- Review migration `0007` SQL before applying it to local PostgreSQL.
- Test scheduling, priority, retries, maximum attempts, concurrency ownership,
  stale recovery, cancellation, idempotency, authorization, and the runner.
