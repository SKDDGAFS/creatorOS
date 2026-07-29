# Backend foundation checklist

- [x] Add application configuration and package structure.
- [x] Add synchronous SQLAlchemy engine and session management.
- [x] Add User, Channel, Video, and VideoMetric models.
- [x] Add root, application health, and database health endpoints.
- [x] Preserve the legacy `main.py` entry point.
- [x] Configure Alembic and add the initial migration.
- [x] Add endpoint and model metadata tests.
- [x] Run tests and migration verification.
- [x] Record the architecture and operating commands.

# Sprint 2 checklist

- [x] Add channel, video, and metric Pydantic schemas.
- [x] Add safe service exceptions and HTTP translation.
- [x] Add channel service and routes.
- [x] Add video and metric services and routes.
- [x] Add metric database constraints and Alembic revision.
- [x] Add isolated API tests.
- [x] Add endpoint and architecture documentation.
- [x] Run tests, route inspection, and migration verification.

# Repository hardening checklist

- [x] Bind the local PostgreSQL port to localhost.
- [x] Make the dashboard backend URL configurable and repair encoding.
- [x] Add pinned Python development tooling and configuration.
- [x] Upgrade and audit dashboard dependencies.
- [x] Add CI and dependency update automation.
- [x] Add security, setup, rollback, and deployment-boundary documentation.
- [x] Run all backend, frontend, migration, Docker, and repository checks.
- [x] Complete the sprint review gate.

# Authentication and ownership checklist

- [x] Add Argon2id password hashing and secure token helpers.
- [x] Add sessions, throttles, reset-token storage, workspaces, and memberships.
- [x] Review and apply ownership migration `0003` to local PostgreSQL.
- [x] Add registration, login, current-user, logout, and workspace endpoints.
- [x] Enforce CSRF, membership roles, and workspace resource isolation.
- [x] Remove client-controlled user ownership from channel creation.
- [x] Add authentication, throttling, CSRF, role, and isolation tests.
- [x] Update API, architecture, setup, and security documentation.

# Analytics expansion checklist

- [x] Make unavailable shared metrics nullable.
- [x] Add shared reach, engagement, conversion, and first-hour fields.
- [x] Add normalized retention, traffic, audience, geography, and discovery data.
- [x] Add platform-matched TikTok, Instagram, and YouTube extensions.
- [x] Compute safe derived rates without persisting stale values.
- [x] Review and apply migration `0004` to local PostgreSQL.
- [x] Add analytics service, validation, authorization, and constraint tests.

# Growth-signal configuration checklist

- [x] Add contextual, workspace-owned, immutable profile versions.
- [x] Add configurable weights and advisory predictor tiers.
- [x] Add sample-size, evidence-volume, and source-confidence handling.
- [x] Return deterministic score, confidence, coverage, and contributions.
- [x] Add authorized profile, catalog, scoring, and deactivation APIs.
- [x] Review and apply migration `0005` to local PostgreSQL.
- [x] Add scoring, validation, isolation, lifecycle, and constraint tests.

# Publishing workflow checklist

- [x] Add workspace-owned publishing jobs and hashed idempotency keys.
- [x] Add centralized publishing state transitions.
- [x] Add human approval, scheduling, cancellation, failure, and retry rules.
- [x] Add immutable transition and workspace activity records.
- [x] Add authorized publishing and approval routes.
- [x] Keep worker transitions internal and avoid external platform calls.
- [x] Review and apply migration `0006` to local PostgreSQL.
- [x] Add state-machine, idempotency, authorization, and lifecycle tests.
- [x] Document workflow semantics and API endpoints.

# Durable job system checklist

- [x] Add workspace-owned jobs and immutable attempt history.
- [x] Add scheduled, prioritized, idempotent enqueueing.
- [x] Add PostgreSQL row-lock claiming and expiring worker leases.
- [x] Add heartbeat, exponential retry, stale recovery, and cancellation.
- [x] Add typed handlers with safe unexpected-error handling.
- [x] Add workspace observability and administrator cancellation APIs.
- [x] Review and apply migration `0007` to local PostgreSQL.
- [x] Add queue, locking, retry, runner, and authorization tests.
- [x] Document queue semantics and operational boundaries.
