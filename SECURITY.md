# Security policy

## Current deployment boundary

CreatorOS is an early local-development project. The API does not yet enforce
authentication, authorization, rate limits, or production secret management.
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

## Required controls before public deployment

- Authentication and record-level authorization.
- Rate limiting and request-size limits.
- Production-safe CORS and trusted-host configuration.
- Centralized secrets, structured logs, and security monitoring.
- PostgreSQL network isolation, TLS, backups, and a tested restore procedure.
