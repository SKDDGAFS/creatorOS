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

## Instagram integration boundary

- Meta app secrets, authorization codes, and access tokens are never stored in
  PostgreSQL or provider request logs.
- OAuth state is random, hash-only at rest, short-lived, user/workspace-bound,
  row-locked during callback, and one-time use.
- The production environment refuses the in-memory development secret store.
- Provider response bodies and token-bearing query parameters are excluded from
  telemetry. Only method, host, path, status, duration, safe outcome, and
  provider request ID are retained.
- Publishing media and cover URLs must be public HTTPS URLs and cannot use
  embedded credentials, localhost, or literal private/reserved addresses.
- Runtime Instagram publishing remains unavailable until the authorized media
  boundary is implemented. No real Meta account or content is used by tests.
- Serving accounts not owned or managed by the app owner requires Meta
  Advanced Access and App Review.

## TikTok integration boundary

- TikTok client secrets, authorization codes, access tokens, and refresh tokens
  never belong in PostgreSQL, API responses, or provider request telemetry.
- OAuth state is random, hash-only at rest, short-lived, one-time, and bound to
  the initiating user and workspace.
- The transport uses fixed HTTPS provider origins, bounded timeouts, disabled
  environment-proxy inheritance, no redirects, and safe error classification.
- Request telemetry excludes query strings, bearer headers, form bodies, and
  response bodies. Only safe operational metadata is persisted.
- Proposed media sources must be public HTTPS URLs and cannot resolve to local,
  private, loopback, link-local, or reserved literal addresses.
- Requesting `video.publish` requires explicit configuration, but runtime
  TikTok publishing remains disabled until the authorized media boundary is
  implemented and reviewed. Tests use fake transports and never publish.

## Analytics worker boundary

- Scheduling and run visibility are workspace scoped. Scheduling requires CSRF
  validation and write access.
- Durable-job payloads contain only a connection UUID. Credential material stays
  behind the existing `CredentialStore` boundary.
- Existing inactive channels are skipped before a provider request is made.
- Provider errors are converted to fixed, safe worker messages. Response bodies,
  tokens, and raw exception text do not enter sync runs or activity events.
- Cursor updates follow successful data writes. Metric snapshot uniqueness makes
  retrying a previously stored page safe.
- The worker uses typed Python callables and has no shell-execution capability.

## AI provider boundary

- The browser has no arbitrary prompt-execution route. Trusted backend workers
  select named prompt versions and typed output models.
- Ollama is restricted to loopback or explicitly configured local hostnames.
  Remote compatible providers require HTTPS and an explicit hostname allowlist,
  reducing SSRF exposure.
- Provider redirects are disabled. URLs with embedded credentials, queries, or
  fragments are rejected, environment proxy settings are ignored, and response
  bodies are capped before parsing.
- Optional API keys use `env://VARIABLE_NAME` references. Key material remains
  in the backend environment and is excluded from API responses and SQL.
- Prompt variables are bounded and are not stored. Output must pass the caller's
  Pydantic schema before it can be returned or persisted.
- Raw provider responses and exception details are never written to failure
  records. Stored error messages come from a fixed safe mapping.
- Workspace token and cost budgets are checked before a provider call. Model
  output remains untrusted and cannot bypass authorization or publishing
  approval.

## Agent-run boundary

- The agent registry is closed to typed recommendation capabilities. It rejects
  publishing and arbitrary shell execution.
- Scheduling stores an immutable prompt-version ID and requires workspace write
  access, CSRF validation, and a hashed durable-job idempotency key.
- Worker output must satisfy the strict recommendation schema before storage.
  It cannot create or approve a publishing transition.
- Input references are bounded resource identifiers and labels, and each must
  resolve inside the active workspace. Referenced or imported content remains
  untrusted data and cannot expand the worker's tools.
- Run, invocation, job, and activity records are workspace scoped. Cancellation
  requires an owner or administrator.
- Raw provider responses and exception details are converted to safe messages
  before they reach run or activity records.

## Research boundary

- Research ingestion stores bounded user- or official-adapter-supplied evidence
  and never fetches submitted URLs. It does not crawl, bypass access controls,
  or circumvent platform rules.
- Public and official evidence links must use credential-free HTTPS. Excerpts,
  metadata, source counts, objective size, and run references are bounded.
- Every source has a source date and freshness window. Stale evidence requires
  explicit opt-in and remains labeled stale.
- The research system prompt must contain the safety contract. Excerpts and
  competitor notes are marked untrusted and cannot grant browsing, shell,
  messaging, publishing, or other tools.
- Structured model output can cite only workspace sources captured by the run.
  Invented citations fail before any finding, hook, or idea is committed.
- Workspace-level fingerprints deduplicate results. Run, source, competitor,
  evidence, finding, hook, idea, invocation, job, and activity access is scoped
  to the active workspace.

## Recommendation boundary

- Recommendations are proposals only and cannot publish or contact platforms.
- Confidence is computed from workspace-owned configurable signal weights,
  sample thresholds, coverage, and source confidence; clients cannot set it.
- Optional research findings and all scoring profiles are verified against the
  active workspace before persistence.
- Result windows and sample counts are validated. Outcome evaluation is
  sample-weighted and always labeled correlational, never causal proof.
- Common absolute causal claims are rejected, and uncertainty is required.
- Status changes follow a closed lifecycle; results require an in-progress or
  completed recommendation.
