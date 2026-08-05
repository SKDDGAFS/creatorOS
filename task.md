# CreatorOS autonomous build checklist

## Sprint A: Repository hardening

- [x] Verify hardening checks and migration integrity.
- [x] Commit and push `feature/repository-hardening`.
- [x] Open draft pull request #2.
- [x] Leave the pull request unmerged.

## Sprint B: Authentication and ownership

- [x] Add secure authentication configuration and cryptographic helpers.
- [x] Add users, sessions, throttles, password-reset, workspace, and membership models.
- [x] Add the reviewed forward-only ownership migration.
- [x] Add authentication and workspace schemas/services/routes.
- [x] Enforce workspace ownership on channels, videos, and metrics.
- [x] Add authentication, CSRF, role, and authorization tests.
- [x] Update API, architecture, security, and setup documentation.
- [x] Run backend quality, migration, dependency, and secret checks.
- [x] Commit, push, and open draft pull request #3.

## Sprint C: Analytics schema expansion

- [x] Make unavailable shared metrics nullable.
- [x] Add shared and first-hour analytics fields.
- [x] Add retention, traffic, audience, geography, and discovery records.
- [x] Add TikTok, Instagram, and YouTube extensions.
- [x] Add safe derived metrics and platform validation.
- [x] Add and review migration `0004`.
- [x] Add analytics service, API, constraint, and authorization tests.
- [x] Update analytics API and architecture documentation.
- [ ] Run quality, migration, dependency, and secret checks.
- [x] Commit, push, and open draft pull request #4.

## Sprint D: Growth-signal configuration

- [x] Add workspace-owned contextual signal profiles.
- [x] Add configurable signal weights and descriptive tiers.
- [x] Add sample-size and source-confidence handling.
- [x] Add deterministic score, confidence, coverage, and contributions.
- [x] Add profile and scoring APIs with workspace authorization.
- [x] Add and review migration `0005`.
- [x] Add service, API, authorization, and constraint tests.
- [x] Update API and architecture documentation.
- [x] Run quality, migration, dependency, and secret checks.
- [x] Commit, push, and open draft pull request #5.

## Sprint E: Publishing workflow

- [x] Add publishing jobs, approvals, transitions, and activity events.
- [x] Add centralized state-machine rules.
- [x] Require approval before scheduling/publishing.
- [x] Add idempotent creation, scheduling, cancellation, failure, and retry.
- [x] Keep multi-record workflow actions transactional.
- [x] Add authorized workflow and activity APIs.
- [x] Add and review migration `0006`.
- [x] Add state-machine, idempotency, authorization, and constraint tests.
- [x] Update API and architecture documentation.
- [x] Run quality, migration, dependency, and secret checks.
- [x] Commit, push, and open draft pull request #6.

## Sprint F: Durable job system

- [x] Add workspace-owned durable jobs and attempt history.
- [x] Add scheduled, prioritized, idempotent enqueueing.
- [x] Add atomic row-lock claiming and expiring worker leases.
- [x] Add heartbeat, exponential retry, and stale-lock recovery.
- [x] Add cancellation and workspace job observability.
- [x] Add a typed handler registry and safe single-job runner.
- [x] Add and review migration `0007`.
- [x] Add queue, retry, locking, runner, and authorization tests.
- [x] Update API and architecture documentation.
- [x] Run quality, migration, dependency, and secret checks.
- [x] Commit, push, and open stacked draft pull request #7.

## Sprint G: Platform adapter framework

- [x] Add the complete typed platform adapter protocol.
- [x] Add provider-neutral DTOs and classified adapter errors.
- [x] Add a credential-store boundary that keeps tokens out of SQL.
- [x] Add workspace-owned connection metadata and cursor persistence.
- [x] Add idempotent platform-operation records.
- [x] Add redacted provider request logging.
- [x] Add adapter registry and fake-adapter contract tests.
- [x] Add and review migration `0008`.
- [x] Update architecture, API, security, and setup documentation.
- [x] Run quality, migration, dependency, and secret checks.
- [x] Commit, push, and open stacked draft pull request #8.

## Sprint H: YouTube integration

- [x] Add secure YouTube OAuth state, PKCE, callback, and refresh foundations.
- [x] Request minimum incremental OAuth scopes.
- [x] Add authenticated channel and uploads-playlist synchronization.
- [x] Add paginated video synchronization and status mapping.
- [x] Add Analytics activity, retention, traffic, and subscriber mapping.
- [x] Add upload validation, dispatch, scheduling, and status polling.
- [x] Add quota tracking and classified Google errors.
- [x] Add disconnect, credential deletion, and token revocation.
- [x] Add adapter contract, OAuth, mapping, pagination, and publishing tests.
- [x] Add and review migration `0009`.
- [x] Add Google Cloud/OAuth setup and limitation documentation.
- [x] Run quality, migration, and secret checks; document unchanged-dependency
  audit carry-forward.
- [x] Commit, push, and open stacked draft pull request #9.

## Sprint I: Instagram integration

- [x] Add user-bound, one-time Instagram OAuth authorization.
- [x] Request minimum read/insights scopes and optional publishing scope.
- [x] Add professional-account and cursor-paginated media synchronization.
- [x] Add account and media insight synchronization with unavailable-value
  semantics.
- [x] Preserve unsupported Reels-tab, Feed, Explore, and profile reach as null.
- [x] Add publishing validation, container creation, finalization, and status
  polling boundaries.
- [x] Add API-call classification and publishing-limit inspection.
- [x] Add disconnect, permission revocation, and credential deletion.
- [x] Add migration `0010` for append-only account insight snapshots.
- [x] Add mocked OAuth, transport, adapter, service, and route tests.
- [x] Document Meta setup, access review, official limitations, and rollback.
- [x] Run quality, migration, and secret checks.
- [x] Commit, push, and open stacked draft pull request #10 without merging.

## Sprint J: TikTok integration

- [x] Add secure TikTok OAuth state, callback, refresh, and revocation foundations.
- [x] Request minimum read scopes and optional publishing scopes.
- [x] Add authorized profile and account-stat synchronization.
- [x] Add cursor-paginated public-video synchronization.
- [x] Map available video metrics and preserve unavailable analytics as null.
- [x] Add creator-info and publishing-validation boundaries.
- [x] Add mocked publish initialization and status polling.
- [x] Add rate-limit and classified TikTok error handling.
- [x] Add disconnect and credential deletion.
- [x] Add OAuth, transport, adapter, service, route, and authorization tests.
- [x] Document TikTok setup, review requirements, restrictions, and unsupported analytics.
- [x] Run quality, migration, dependency, and secret checks.
- [x] Commit, push, and open stacked draft pull request #11 without merging.
