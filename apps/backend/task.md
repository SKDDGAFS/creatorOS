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

# Platform adapter framework checklist

- [x] Add typed account, sync, metrics, publish, status, and revoke contracts.
- [x] Add classified provider errors and adapter registry.
- [x] Add an encrypted credential-store protocol and keep tokens out of SQL.
- [x] Add workspace-owned connection metadata and sync cursors.
- [x] Add fingerprint-bound idempotent operation records.
- [x] Add recursively redacted request logging without queries or responses.
- [x] Review and apply migration `0008` to local PostgreSQL.
- [x] Add fake adapter, credential, redaction, cursor, and operation tests.
- [x] Document security and external-provider boundaries.

# YouTube integration checklist

- [x] Add state-hashed, PKCE-protected, user-bound OAuth authorization.
- [x] Add minimum/incremental read, analytics, and optional upload scopes.
- [x] Add token exchange, refresh, revocation, and safe error classification.
- [x] Add channel, uploads-playlist, video, and opaque-cursor synchronization.
- [x] Add activity, retention, traffic-source, and subscriber analytics mapping.
- [x] Preserve rewatch retention ratios above one and unavailable metric nulls.
- [x] Add upload validation, resumable dispatch, and status polling boundaries.
- [x] Add daily quota accounting and redacted request telemetry.
- [x] Add authorized integration routes and safe response schemas.
- [x] Review and apply migration `0009` to local PostgreSQL.
- [x] Add mocked OAuth, transport, sync, publishing, quota, and route tests.
- [x] Document Google setup, provider limitations, and rollback.

# Analytics worker checklist

- [x] Add workspace-owned run state linked to durable jobs and connections.
- [x] Add idempotent scheduling and connection health APIs.
- [x] Register the typed analytics handler with the durable runner.
- [x] Synchronize provider data through existing service boundaries.
- [x] Add safe retries, inactive-channel skipping, and activity events.
- [x] Make captured metric snapshots idempotent.
- [x] Add migration `0011`, tests, and documentation.
- [x] Complete tests, lint, typing, dependency, offline migration, diff, and
  secret verification.
- [ ] Apply migration `0011` and run the live PostgreSQL schema drift check when
  Docker is available.

# AI provider router checklist

- [x] Add provider-neutral structured generation contracts.
- [x] Add local Ollama and optional OpenAI-compatible transports.
- [x] Add workspace provider configuration and SSRF-safe URL policy.
- [x] Add versioned prompts and a constrained renderer.
- [x] Add retries, fallback, schema validation, and idempotent result reuse.
- [x] Add token/cost budgets, usage records, and health checks.
- [x] Add authorized management and observability APIs.
- [x] Add migration `0012`, mocked tests, and documentation.
- [x] Complete tests, lint, typing, dependency, offline migration, diff, and
  secret verification.
- [ ] Apply migration `0012` and run live schema drift when Docker is available.

# Agent-run framework checklist

- [x] Add a closed registry for strategy, copy, social, video-analysis, and
  token-optimization agents.
- [x] Enforce recommendation-only capabilities with no publishing or shell
  execution.
- [x] Add workspace-owned agent runs linked to an exact prompt version, durable
  job, optional AI invocation, requester, and activity events.
- [x] Record objective, typed input references, status, timestamps, model,
  estimated cost, strict output, confidence, and safe errors.
- [x] Add idempotent scheduling, filtered history, detail, capability, and
  administrator cancellation APIs.
- [x] Add a durable worker with AI routing, schema validation, safe retry, and
  prompt-version reproducibility.
- [x] Add migration `0013`, fake-provider tests, and security/API/operations
  documentation.
- [x] Complete 105 tests, lint, typing, offline migration, and diff checks.
- [ ] Apply migration `0013` and run live PostgreSQL schema drift when Docker is
  available.

# Research worker checklist

- [x] Add workspace-owned dated research sources with HTTPS evidence links,
  bounded excerpts/metadata, freshness windows, and content deduplication.
- [x] Add workspace-owned platform competitor records.
- [x] Add idempotent durable research runs tied to an exact prompt version and
  optional successful AI invocation.
- [x] Require an explicit stale-source opt-in and record fresh/stale counts.
- [x] Mark excerpts and competitor notes as untrusted prompt data and require a
  system safety contract.
- [x] Validate structured findings, evidence links, hooks, and content ideas;
  reject citations outside the scheduled source set.
- [x] Deduplicate artifacts per workspace while tracking first/last seen runs.
- [x] Add workspace APIs, administrator cancellation, activity events,
  migration `0014`, tests, and documentation.
- [x] Complete 109 tests, lint, typing, and offline migration verification.
- [ ] Apply migration `0014` and run live PostgreSQL schema drift when Docker is
  available.

# Strategy and recommendation checklist

- [x] Add workspace recommendations with action, rationale, expected effect,
  uncertainty, impact, effort, risk, goal label, status, and deduplication.
- [x] Link metric evidence and optional workspace research findings.
- [x] Reuse configurable growth-signal weights to compute confidence and sample
  size server-side.
- [x] Enforce a closed recommendation lifecycle and correlational language.
- [x] Add result measurements with valid windows and outcome evaluation.
- [x] Persist sample-weighted change, confidence, conclusion, and uncertainty
  interpretation.
- [x] Add migration `0015`, authorized APIs, tests, and documentation.
- [ ] Apply migration `0015` and run live PostgreSQL schema drift when Docker is
  available.
