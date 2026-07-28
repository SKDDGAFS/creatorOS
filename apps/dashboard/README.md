# CreatorOS dashboard

This Next.js application is the local CreatorOS dashboard.

Copy `.env.example` to `.env.local` before starting it. `NEXT_PUBLIC_API_URL`
selects the backend origin and defaults to `http://127.0.0.1:8000`.

The `NEXT_PUBLIC_` prefix makes the value visible in browser code, so it must
never contain a secret.

## Local commands

```powershell
Copy-Item .env.example .env.local
npm ci
npm run dev
```

Open `http://localhost:3000`.

Verification:

```powershell
npm run lint
.\node_modules\.bin\tsc.cmd --noEmit --incremental false
npm run build
npm audit --audit-level=high
```

Public deployment remains blocked until the security controls listed in the root
`SECURITY.md` are implemented.
