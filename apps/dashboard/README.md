# CreatorOS dashboard

This Next.js application is the private single-user CreatorOS interface.
Navigation contains Home, Schedule, Content, Connections, and Settings.
Content reads existing videos with pagination and loading, empty, and retry states.
Scheduling, uploads, recommendations, and platform connections are clearly marked
as unavailable. Settings displays the browser timezone; it does not save a timezone.
There is no sign-in or analytics UI.

Copy `.env.example` to `.env.local` before starting it. `NEXT_PUBLIC_API_URL`
selects the backend origin and defaults to `http://127.0.0.1:8000`.

The `NEXT_PUBLIC_` prefix makes the value visible in browser code, so it must
never contain a secret.

## Local commands

```powershell
Copy-Item .env.example .env.local # Only on first setup.
npm ci
npm run dev
```

Open `http://localhost:3000`.

The dev and production start scripts bind to `127.0.0.1`. Open the app using
`localhost` to match the default backend CORS origin. If you use another origin,
update `FRONTEND_ORIGIN` explicitly. The UI uses system fonts and needs no Google
Fonts request during the build.

Verification:

```powershell
npm run lint
.\node_modules\.bin\tsc.cmd --noEmit --incremental false
npm run build
npm audit --audit-level=high
```

Public deployment remains blocked until the security controls listed in the root
`SECURITY.md` are implemented.
