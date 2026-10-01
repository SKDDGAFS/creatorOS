# CreatorOS

CreatorOS is currently a private single-user content scheduling and publishing
assistant. Its goal is to help you prepare content, recommend posting times,
and schedule publishing. Performance data will quietly improve scheduling.

## Current status

The repository contains:

- a FastAPI backend with synchronous SQLAlchemy, Psycopg 3, and Alembic;
- local PostgreSQL 16 through Docker Compose;
- channel, video, and metric APIs;
- a minimal Next.js interface: Home, Schedule, Content, Connections, Settings;
- a paginated Content library that reads existing Video API records.

Home and Schedule clearly mark future scheduling and recommendation features.
Connections shows placeholders for YouTube, Instagram, and TikTok, in that order.
Settings displays local mode and the browser timezone. Uploads, metadata
generation, scheduling persistence, recommendations, OAuth, and publishing are
not implemented yet. There are no fabricated posting times or performance data.

There is no CreatorOS login. The existing User table remains for compatibility
with channel ownership references; it does not create a sign-in requirement.
Future platform OAuth will authorize publishing separately from local app access.

CreatorOS runs locally on your own machine. Keep its unauthenticated API and
interface private; see `SECURITY.md` for the deployment boundary.

## Local setup

Requirements: Docker Desktop, Python 3.14, and Node.js 22.

Start PostgreSQL:

```powershell
cd .\apps\backend
Copy-Item .env.example .env # Only on first setup; preserve an existing .env.
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
Copy-Item .env.example .env.local # Only if it does not already exist.
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

The next phase is a local content preparation and scheduling queue with manual
time selection. See `docs/SCHEDULING.md` for the proposed record and service
boundaries. Platform integration requires a separate sprint.
