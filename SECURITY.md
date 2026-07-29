# Security policy

## Current deployment boundary

CreatorOS is an early local-development project. The API enforces opaque
database-backed sessions, Argon2id password hashing, CSRF checks on authenticated
writes, login throttling, workspace roles, and record-level ownership. It does
not yet provide production secret management, general request limits, security
monitoring, or hardened reverse-proxy controls. Do not expose the dashboard, API,
or PostgreSQL service to the public internet.

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
- Platform credentials exist in memory only as redacted `SecretStr` values and
  must be stored through an encrypted `CredentialStore` implementation.
  PostgreSQL connection records contain only a vault reference.
- Provider request logs discard URL queries and response bodies and recursively
  redact authorization, cookie, token, password, secret, credential, OAuth
  verifier, and API-key fields.
- YouTube now supplies minimum scopes, a hashed single-use state, PKCE,
  callback-user binding, refresh, and revocation. The included credential store
  is volatile development/test memory only. Do not enable a production or
  public OAuth flow until an encrypted external secret-store implementation is
  configured and reviewed.
- OAuth callback URLs must be exact. Production configuration rejects a
  non-HTTPS YouTube redirect URI.
- Provider telemetry stores no response body or URL query. OAuth token endpoint
  form bodies and bearer headers are never passed to persistence.

## Required controls before public deployment

- Rate limiting and request-size limits.
- Production-safe CORS and trusted-host configuration.
- Centralized secrets, structured logs, and security monitoring.
- PostgreSQL network isolation, TLS, backups, and a tested restore procedure.

## Authentication controls

- Session and CSRF tokens are generated from cryptographically secure randomness.
  Only SHA-256 token hashes are stored in PostgreSQL.
- The session cookie is HTTP-only and both cookies use `SameSite=Lax`. Set
  `SESSION_COOKIE_SECURE=true` in any HTTPS environment; production startup fails
  when it is false.
- Login failures use a generic message and are throttled by a one-way hash of the
  normalized email address.
- Workspace IDs never grant access by themselves. Every request verifies an
  active user session and membership; writes additionally require CSRF and a
  non-viewer role.
- Password-reset tokens have storage and expiry foundations only. No email
  delivery or public reset endpoint is enabled in this sprint.
