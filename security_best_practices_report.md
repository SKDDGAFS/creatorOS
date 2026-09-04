# CreatorOS security review

Reviewed on 2026-09-05. The scope covered the tracked repository and all 456
reachable Git blob objects. The FastAPI application and Next.js dashboard were
reviewed in full. Dependency manifests and CI were checked too. Deployment
examples were reviewed separately.

## Executive summary

No critical or high-severity vulnerability was confirmed. The current tree and
reachable Git history produced zero high-confidence secret matches. This scan
looked for common provider tokens, private keys, live payment keys, JWTs, and
credential-shaped assignments without printing candidate values.

Four fixable issues were found and corrected. Production configuration now
fails closed, the API validates hosts and narrows CORS, database URLs are
redacted by Pydantic, API docs close in production, and both web services return
baseline browser security headers. Next.js and PostCSS were upgraded to versions
that leave `npm audit` at zero known vulnerabilities.

CreatorOS remains a local-development application. Request-size controls,
general rate limits, an external secret store, and production monitoring are
still required before exposing it to the public internet.

## Resolved findings

### COS-001: Production API configuration allowed avoidable exposure

- Rule IDs: FASTAPI-DEPLOY-002, FASTAPI-OPENAPI-001, FASTAPI-CORS-001,
  FASTAPI-HOST-001
- Severity: Medium
- Location: `apps/backend/app/core/config.py:77-104` and
  `apps/backend/app/main.py:18-61`
- Evidence: The previous app used environment-controlled debug mode, left
  OpenAPI endpoints at their defaults, had no trusted-host middleware, and
  allowed every CORS method and header. The revised settings reject debug,
  insecure frontend origins, empty host lists, and wildcard production hosts.
- Impact: A bad production environment could disclose API structure or accept
  unexpected host and cross-origin request metadata.
- Fix: Production docs are disabled. `TrustedHostMiddleware` uses an explicit
  host list. CORS now allows one configured origin and only the methods and
  headers used by CreatorOS.
- Mitigation: Keep equivalent host and CORS checks at the reverse proxy.
- False-positive notes: Edge controls may have covered some of this, but none
  were present in the repository.

### COS-002: Database credentials were easy to expose through settings output

- Rule ID: FASTAPI-DEPLOY-002
- Severity: Medium
- Location: `apps/backend/app/core/config.py:23`,
  `apps/backend/app/db/session.py:10`, and `apps/backend/alembic/env.py:12`
- Evidence: `DATABASE_URL` was a plain string. It can contain a database
  password and could appear if settings were printed or inspected.
- Impact: Operational logs or error tooling could capture database credentials.
- Fix: The value is now a Pydantic `SecretStr`; database and migration code
  unwrap it only where a connection URL is required.
- Mitigation: Use a production secret manager and redact configuration in the
  logging pipeline.
- False-positive notes: No code currently logs the settings object, so this was
  a preventive fix.

### COS-003: Browser security headers were absent

- Rule IDs: FASTAPI-HEADERS-001, REACT-HEADERS-001, NEXT-HEADERS-001
- Severity: Medium
- Location: `apps/backend/app/main.py:46-61` and
  `apps/dashboard/next.config.ts:5-25`
- Evidence: Neither service set clickjacking, content-sniffing, referrer, or
  browser-feature controls in repository configuration.
- Impact: A future deployment would lack useful browser defenses if the edge did
  not add them.
- Fix: Both services now set `X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy`, and `Permissions-Policy`. CSP blocks framing and object
  embedding; the production API uses `default-src 'none'`.
- Mitigation: Verify the final response headers after a real deployment because
  a proxy can replace them.
- False-positive notes: No deployed edge configuration was available to inspect.

### COS-004: Frontend dependency advisory

- Rule IDs: NEXT-SUPPLY-001, REACT-SUPPLY-001
- Severity: Medium
- Location: `apps/dashboard/package.json:13` and
  `apps/dashboard/package.json:28-29`
- Evidence: `npm audit` reported three moderate findings caused by PostCSS
  8.5.22 through the frontend toolchain.
- Impact: The advisory describes unintended local source-map file reads during
  CSS processing when an attacker controls the source-map annotation.
- Fix: Next.js is now 16.3.4, PostCSS is 8.5.26, and Sharp is 0.35.4. The lockfile
  was regenerated. `npm audit --audit-level=moderate` now reports zero findings.
- Mitigation: Dependabot and the CI audit remain enabled.
- False-positive notes: Exploitability in this app was limited because users do
  not supply CSS build input, but patching removed the vulnerable dependency.

## Remaining production blockers

### COS-101: General request and abuse limits are not implemented

- Severity: Medium if publicly deployed
- Location: `SECURITY.md:45-49`
- Evidence: Login throttling exists, but there is no repository-wide body-size
  limit or general rate limiter for expensive endpoints.
- Impact: A public service could be subjected to oversized requests or repeated
  expensive work.
- Fix: Add proxy-level body limits and rate limits. Add per-user application
  limits for AI and research routes, then cover OAuth and job scheduling.
- Mitigation: Keep the application bound to local interfaces until these controls
  are tested.
- False-positive notes: A future hosting platform may provide these controls;
  verify them with live tests.

### COS-102: Production operations are incomplete

- Severity: Medium if publicly deployed
- Location: `SECURITY.md:45-49`
- Evidence: The project has no production secret manager, central security logs,
  alerting, or tested database backup and restore process.
- Impact: A credential or service incident would be harder to contain and
  investigate.
- Fix: Complete the controls listed in `SECURITY.md` before deployment.
- Mitigation: Real provider credentials and publishing stay disabled in local
  development.
- False-positive notes: External infrastructure was outside this repository
  review.

## Verification performed

- Backend: Ruff, MyPy, 119 Pytest tests, `pip check`, and `pip-audit` passed.
- Frontend: Biome, TypeScript, production build, and npm audit passed.
- Database: Alembic has one head (`0015`) and generated the full offline upgrade
  SQL successfully.
- Secret review: zero high-confidence matches in the current tree and all 456
  reachable historical blobs.

Docker was not installed on the review machine, so a live PostgreSQL migration,
`alembic check`, and the full Docker Compose startup could not be run locally.
