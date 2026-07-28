# CreatorOS

CreatorOS is an early-stage intelligent assistant for creator research,
publishing, analytics, and growth.

## Current status

The repository contains:

- a FastAPI backend with synchronous SQLAlchemy, Psycopg 3, and Alembic;
- local PostgreSQL 16 through Docker Compose;
- session-based authentication, CSRF protection, and workspace roles;
- workspace-owned channel, video, and metric APIs;
- a Next.js dashboard connected to the backend.

CreatorOS is for local development only. Authentication and record ownership are
implemented, but production secret management, edge request limits, monitoring,
and platform integrations are not. Do not publish the application to the
internet yet; see `SECURITY.md`.

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
