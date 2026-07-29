# YouTube integration setup

CreatorOS contains a YouTube adapter and OAuth flow, but this repository does
not contain Google credentials and no automated test contacts Google. Complete
the following checklist only with a development/test Google account and only
after deciding to enable the integration manually.

## Current safety boundary

- OAuth uses an authorization-code web-server flow with a random, hashed,
  single-use state value and PKCE `S256`.
- The callback is tied to the signed-in CreatorOS user that started it.
- PostgreSQL stores account metadata, granted scopes, token expiry, OAuth-state
  hashes, secret-store references, request metadata, and quota totals. It never
  stores access tokens, refresh tokens, client secrets, authorization codes, or
  PKCE verifiers.
- The included `InMemoryPlatformSecretStore` is volatile and development/test
  only. Restarting the backend loses credentials and pending verifier material.
  Production startup refuses to use it; a production encrypted secret-manager
  implementation is required.
- `YOUTUBE_ENABLE_PUBLISHING` defaults to `false`. The runtime media source is
  also intentionally disabled until CreatorOS has the authorized media-storage
  boundary from Sprint U. Therefore this sprint cannot publish real content.
- CreatorOS does not create projects, consent screens, credentials, accounts,
  uploads, or paid services automatically.

## Google Cloud checklist

1. Create or select a Google Cloud project that is dedicated to the intended
   CreatorOS environment.
2. Enable **YouTube Data API v3** and **YouTube Analytics API**.
3. Configure the Google Auth Platform branding, audience, and data-access
   sections.
4. For an external app in testing, add only the development Google accounts as
   test users.
5. Add these minimum scopes:

   - `https://www.googleapis.com/auth/youtube.readonly`
   - `https://www.googleapis.com/auth/yt-analytics.readonly`

6. Add `https://www.googleapis.com/auth/youtube.upload` only if publishing has
   been explicitly enabled and the media/publishing safety controls are ready.
7. Create an OAuth client with application type **Web application**.
8. Add the exact local redirect URI:

   `http://127.0.0.1:8000/api/integrations/youtube/oauth/callback`

9. Keep the client secret outside Git and outside browser-visible environment
   variables. Never place it in a `NEXT_PUBLIC_*` variable.
10. Before any public or multi-user use, complete the consent-screen publishing,
    verification, privacy-policy, and domain requirements shown in the current
    Google Cloud console. CreatorOS does not claim that a Google review will be
    approved.

Current official references:

- OAuth web-server flow:
  https://developers.google.com/identity/protocols/oauth2/web-server
- YouTube server-side authorization:
  https://developers.google.com/youtube/v3/guides/auth/server-side-web-apps
- OAuth security practices:
  https://developers.google.com/identity/protocols/oauth2/resources/best-practices
- YouTube Data API channel resource:
  https://developers.google.com/youtube/v3/docs/channels
- Uploads playlist pages:
  https://developers.google.com/youtube/v3/docs/playlistItems/list
- Video resources and status:
  https://developers.google.com/youtube/v3/docs/videos
- Video upload:
  https://developers.google.com/youtube/v3/docs/videos/insert
- Analytics targeted queries:
  https://developers.google.com/youtube/analytics/reference/reports/query
- Supported channel reports:
  https://developers.google.com/youtube/analytics/channel_reports
- Analytics dimensions and metrics:
  https://developers.google.com/youtube/analytics/dimensions
  and https://developers.google.com/youtube/analytics/metrics
- Data API errors:
  https://developers.google.com/youtube/v3/docs/errors

Re-check these pages before enabling a real integration because provider
requirements and quotas can change.

## Local configuration

Copy `apps/backend/.env.example` to `apps/backend/.env`, then set:

```dotenv
YOUTUBE_CLIENT_ID=your-development-web-client-id
YOUTUBE_CLIENT_SECRET=your-development-web-client-secret
YOUTUBE_OAUTH_REDIRECT_URI=http://127.0.0.1:8000/api/integrations/youtube/oauth/callback
YOUTUBE_ENABLE_PUBLISHING=false
YOUTUBE_HTTP_TIMEOUT_SECONDS=30
YOUTUBE_ANALYTICS_LOOKBACK_DAYS=28
```

Both client values must be set together. A configured production environment
requires an HTTPS redirect URI. Do not commit `.env`.

Apply the local migration and start the API:

```powershell
cd .\apps\backend
.\venv\Scripts\alembic.exe upgrade head
.\venv\Scripts\uvicorn.exe main:app --reload
```

The active session must be a workspace owner or administrator. The OAuth-start
request also requires the normal CreatorOS CSRF header. Google redirects back
through a top-level GET; that callback requires the same signed-in CreatorOS
session and validates the single-use state instead of accepting a workspace ID
from the browser.

## Implemented behavior

- Authenticated-channel discovery uses `channels.list(mine=true)` and reads the
  channel's uploads playlist.
- Video synchronization pages through `playlistItems.list`, then hydrates up to
  50 IDs through `videos.list`.
- Targeted analytics synchronize activity, retention, traffic-source, and
  subscribed/unsubscribed-view data.
- Unavailable values stay `null`; a reported zero remains zero.
- `audienceWatchRatio` can legitimately exceed `1` after rewatches, so CreatorOS
  preserves values above 100 percent instead of clamping them.
- Reach-report thumbnail impressions and click-through rate are not exposed by
  the targeted Analytics query used here. The newer bulk Reporting API has
  separate reach reports, so `reported_impressions_ctr` remains `null` until a
  compliant bulk-report ingestion worker is implemented.
- Publishing validation requires the upload scope, an explicit made-for-kids
  decision, a valid privacy state, a future schedule, and private visibility
  for scheduled uploads.
- The HTTP transport supports resumable upload initiation and status polling,
  but the application runtime cannot open media until the safe media-storage
  sprint is complete.
- Data API, Analytics API, and video-upload usage are recorded in separate
  daily buckets. These are CreatorOS accounting estimates, not a replacement
  for the quota values shown in Google Cloud.
- Disconnect requests revoke the refresh/access token before marking the local
  connection disconnected and deleting the credential-store entry.

## Known provider limitations

- YouTube may return no analytics for recent dates, small audiences, privacy
  thresholds, unsupported report combinations, or accounts that lack access.
- Some metrics are not available for every video type or historical period.
- A Google API project that has not passed the required upload audit can have
  uploads forced to private. CreatorOS does not bypass this restriction.
- OAuth refresh tokens might not be returned on every authorization. The local
  implementation requests offline access and explicit consent; a missing or
  revoked refresh token requires reconnection.
- Publishing idempotency is enforced by CreatorOS platform-operation records.
  YouTube does not accept CreatorOS's idempotency key as a provider header.
- Instagram and TikTok are separate future provider sprints and are not
  configured by this guide.

## Verification without Google

```powershell
cd .\apps\backend
.\venv\Scripts\pytest.exe -q tests\test_youtube_integration.py
.\venv\Scripts\ruff.exe check app tests alembic main.py
.\venv\Scripts\mypy.exe app alembic main.py
.\venv\Scripts\alembic.exe current
.\venv\Scripts\alembic.exe check
```

The integration tests use fake adapters and `httpx2.MockTransport`. They do not
need credentials, consume quota, open a browser, revoke a real token, or upload
content.

## Migration and rollback

Revision `0009` adds single-use OAuth-state and daily platform-quota tables and
relaxes the retention constraint to allow legitimate ratios above `1`.

Before any downgrade:

1. Stop the API and workers.
2. Back up the database.
3. Confirm no authorization callback is in progress.
4. Review `alembic downgrade 0008 --sql`.
5. Check for stored retention ratios above `1`; revision `0008` cannot represent
   them and the downgrade constraint would reject that data.
6. Export any quota history that must be retained.

Downgrading to `0008` drops the OAuth-state and quota tables and restores the
old retention upper bound. It is intentionally not run automatically.
