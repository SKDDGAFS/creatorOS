# Security policy

## Current deployment boundary

CreatorOS is a private single-user local application. CreatorOS-level login is
intentionally absent. The API does not enforce authentication, authorization,
rate limits, or production secret management. Platform OAuth remains a separate
future concern and does not make the local API safe for public access.
Do not expose the dashboard, API, or PostgreSQL service to the public internet.

The credentials in `apps/backend/docker-compose.yml` and `.env.example` are
development defaults only. Production credentials must be unique, stored in a
secret manager, and rotated independently of source control.

## Reporting a vulnerability

Use the repository Security tab to submit a private vulnerability report. Do not
include credentials, tokens, personal data, or exploit details in a public issue.

## Secret handling

- Commit `.env.example` files only; never commit `.env` files.
- Keep GitHub secret scanning and push protection enabled.
- If a secret is exposed, revoke or rotate it first, then remove it from code and
  history. Deleting the visible file is not sufficient.
- Review dependency audit results before merging dependency changes.
- OAuth state and platform access/refresh tokens are encrypted by the backend
  before database writes. `CREDENTIAL_ENCRYPTION_KEY` stays in the local backend
  environment and is never returned through API schemas or browser storage.
- Back up the encryption key separately from the database. Losing it makes
  stored credentials unrecoverable; rotating it requires re-encrypting existing
  records before replacing the old key.

## Required controls before public deployment

- Authentication and record-level authorization.
- Rate limiting and request-size limits.
- Production-safe CORS and trusted-host configuration.
- Centralized secrets, structured logs, and security monitoring.
- PostgreSQL network isolation, TLS, backups, and a tested restore procedure.
