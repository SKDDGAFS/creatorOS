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
- [x] Run quality, migration, dependency, and secret checks.
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
