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
