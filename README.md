# CreatorOS

CreatorOS is an early-stage intelligent assistant for creator research,
publishing, analytics, and growth.

## Current status

The repository contains:

- a FastAPI backend with synchronous SQLAlchemy, Psycopg 3, and Alembic;
- local PostgreSQL 16 through Docker Compose;
- session-based authentication, CSRF protection, and workspace roles;
- workspace-owned channel, video, and metric APIs;
- an approval-gated publishing workflow that records intent without contacting
  external platforms;
- a PostgreSQL-backed durable job queue with retries, leases, and attempt
  history;
- a typed platform-adapter framework with credential-store isolation, cursors,
  idempotency, and redacted request logs;
- a credential-independent YouTube integration with secure OAuth state/PKCE,
  channel and video synchronization, analytics mappings, quota telemetry,
  upload validation, and mocked adapter tests;
- a credential-independent Instagram professional-account integration with
  secure OAuth state, account/media synchronization, append-only insights,
  publishing-limit/status foundations, and mocked adapter tests;
- a credential-independent TikTok integration with secure OAuth state, profile
  and video synchronization, public metric mappings, publishing validation,
  quota telemetry, and mocked transport tests;
- a Next.js dashboard connected to the backend.

CreatorOS is for local development only. Authentication and record ownership are
implemented, but production secret management, edge request limits, monitoring,
and production-ready platform credentials are not. Do not publish the
application to the internet yet; see `SECURITY.md`.

## Local setup

Requirements: Docker Desktop, Python 3.14, and Node.js 22.

Start PostgreSQL:

```powershell
cd .\apps\backend
Copy-Item .env.example .env
docker compose up -d
```

Create the backend environment and apply migrations:

```powershell
py -3.14 -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\venv\Scripts\alembic.exe upgrade head
```

Run the backend:

```powershell
.\venv\Scripts\uvicorn.exe main:app --reload
```

In another terminal, run the dashboard:

```powershell
cd .\apps\dashboard
Copy-Item .env.example .env.local
npm ci
npm run dev
```

Open `http://localhost:3000`. The API documentation is at
`http://127.0.0.1:8000/docs`.

Real YouTube, Instagram, and TikTok credentials are not committed or used by
tests. Exact manual setup and limitations are documented in
`docs/YOUTUBE_SETUP.md`, `docs/INSTAGRAM_SETUP.md`, and
`docs/TIKTOK_SETUP.md`. The included secret store is local/test only and real
publishing remains disabled.

## Verification

Backend:

```powershell
cd .\apps\backend
.\venv\Scripts\ruff.exe check app tests alembic main.py
.\venv\Scripts\mypy.exe app alembic main.py
.\venv\Scripts\pytest.exe -q
.\venv\Scripts\pip-audit.exe -r requirements.lock
```

Dashboard:

```powershell
cd .\apps\dashboard
npm run lint
.\node_modules\.bin\tsc.cmd --noEmit --incremental false
npm run build
npm audit --audit-level=high
```

## Safe rollback

- Stop local services with `docker compose down`. This preserves the database
  volume. Do not add `-v` unless you intentionally want to erase local data.
- Review Alembic downgrade SQL before rolling back a schema revision. Database
  backups are required before production migration changes.
- Revert application changes through a reviewed Git commit instead of deleting
  working files manually.

Architecture details are in `apps/backend/system_architecture.md`; API behavior
is documented in `apps/backend/API.md`.
