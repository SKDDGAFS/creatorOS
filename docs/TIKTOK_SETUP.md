# TikTok integration setup

CreatorOS uses TikTok Login Kit OAuth v2, the Display API, and the Content
Posting API contracts. Automated tests use an injected fake transport; they do
not contact TikTok or publish content.

## Create and configure the TikTok app

1. Create an app in the TikTok for Developers portal.
2. Add Login Kit and the Display API products.
3. Register the exact redirect URI used by the backend. For local development:
   `http://127.0.0.1:8000/api/integrations/tiktok/oauth/callback`.
4. Request `user.info.basic`, `user.info.profile`, `user.info.stats`, and
   `video.list`. Request `video.publish` only when the app has an approved
   publishing use case.
5. Copy `.env.example` to `.env` and configure:

   ```text
   TIKTOK_CLIENT_KEY=your-client-key
   TIKTOK_CLIENT_SECRET=your-client-secret
   TIKTOK_OAUTH_REDIRECT_URI=http://127.0.0.1:8000/api/integrations/tiktok/oauth/callback
   TIKTOK_ENABLE_PUBLISHING=false
   TIKTOK_HTTP_TIMEOUT_SECONDS=30
   ```

Keep the client secret out of Git. Production requires an HTTPS redirect URI
and an encrypted external implementation of the platform secret-store protocol.
The included in-memory store is for local development and tests only.

## Supported behavior

- One-time, short-lived OAuth state is stored as a hash and bound to the user
  and workspace that started authorization.
- Access and refresh tokens stay behind the secret-store interface. PostgreSQL
  stores only a credential reference and safe account metadata.
- Channel/profile, owned-video pages, account totals, and public video counters
  can be synchronized.
- Provider cursors remain opaque and are persisted per connection.
- Missing metrics remain `null`; the Display API does not expose owner traffic
  sources, audience retention, or impression click-through rate.
- Refresh, revocation, quota accounting, and redacted request telemetry are
  implemented through the isolated transport boundary.

## Publishing boundary

`TIKTOK_ENABLE_PUBLISHING` controls whether OAuth may request `video.publish`.
It does not enable application publishing. Runtime dispatch stays disabled until
CreatorOS has the Sprint U authorized media-storage boundary.

The adapter can validate a proposed direct post using TikTok's current creator
information. It requires explicit privacy selection, checks the creator's
allowed privacy options and video-duration limit, honors disabled interaction
settings, and accepts only public HTTPS media URLs. `PULL_FROM_URL` additionally
requires TikTok verification of the source domain or URL prefix.

Unaudited TikTok clients are subject to TikTok's private-only posting rules.
CreatorOS must show the latest creator information and obtain the creator's
explicit consent before any future dispatch. Tests never make a real post.

## Manual verification checklist

1. Start PostgreSQL and apply `alembic upgrade head`.
2. Configure a development TikTok app and exact redirect URI.
3. Start the backend and sign in to a workspace as an owner or administrator.
4. Start OAuth with `POST /api/integrations/tiktok/oauth/start` and complete the
   browser callback as the same signed-in user.
5. Synchronize channel, videos, account insights, and one video's metrics.
6. Confirm API responses and request logs contain no tokens, authorization
   codes, query strings, response bodies, or client secret.
7. Disconnect and confirm the connection is marked disconnected and the secret
   reference is removed.

## Official references

- [Login Kit for Web](https://developers.tiktok.com/doc/login-kit-web)
- [TikTok API scopes](https://developers.tiktok.com/doc/tiktok-api-scopes)
- [OAuth token management](https://developers.tiktok.com/doc/oauth-user-access-token-management)
- [Display API overview](https://developers.tiktok.com/doc/display-api-overview/)
- [Video list endpoint](https://developers.tiktok.com/doc/tiktok-api-v2-video-list)
- [Direct Post API](https://developers.tiktok.com/doc/content-posting-api-reference-direct-post)
- [Creator information endpoint](https://developers.tiktok.com/doc/content-posting-api-reference-query-creator-info)
- [Content sharing guidelines](https://developers.tiktok.com/doc/content-sharing-guidelines/)
