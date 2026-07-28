# CreatorOS authenticated API

The local API defaults to `http://127.0.0.1:8000`; OpenAPI documentation is at
`/docs`.

## Authentication

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/auth/register` | Create a user, personal workspace, and session |
| `POST` | `/api/auth/login` | Create a session |
| `GET` | `/api/auth/me` | Read the active user |
| `POST` | `/api/auth/logout` | Revoke the active session |

Register:

```json
{
  "email": "creator@example.com",
  "display_name": "Creator",
  "password": "a long unique passphrase"
}
```

Register and login set `creatoros_session` as an HTTP-only cookie and
`creatoros_csrf` as a readable cookie. Their response also includes
`csrf_token`. Send that value as `X-CSRF-Token` on authenticated write requests.
The browser must include credentials.

## Workspaces and authorization

| Method | Path | Access |
| --- | --- | --- |
| `GET` | `/api/workspaces` | Authenticated memberships |
| `POST` | `/api/workspaces` | Authenticated + CSRF |
| `POST` | `/api/workspaces/{workspace_id}/members` | Owner/admin + CSRF |

All channel, video, and metric requests require:

```text
X-Workspace-ID: 11111111-1111-1111-1111-111111111111
```

The API verifies membership. Roles are `owner`, `admin`, `member`, and `viewer`;
viewers cannot write. A resource outside the active workspace is returned as
not found so records cannot be enumerated across workspaces.

## Channels

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/channels` | Create in the active workspace |
| `GET` | `/api/channels` | List/filter active-workspace channels |
| `GET` | `/api/channels/{channel_id}` | Get one channel |
| `PATCH` | `/api/channels/{channel_id}` | Partially update one channel |

Create request:

```json
{
  "platform": "youtube",
  "platform_channel_id": "UC-example",
  "name": "CreatorOS",
  "handle": "@creatoros",
  "is_active": true
}
```

The authenticated user and workspace become the owners; clients cannot provide
`user_id`. Supported platforms are `youtube`, `tiktok`, and `instagram`. List
filters are `platform`, `is_active`, `limit`, and `offset`.

## Videos and metric snapshots

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/videos` | Create for an active-workspace channel |
| `GET` | `/api/videos` | List/filter videos |
| `GET` | `/api/videos/{video_id}` | Get one video |
| `PATCH` | `/api/videos/{video_id}` | Partially update one video |
| `POST` | `/api/videos/{video_id}/metrics` | Append a metric snapshot |
| `GET` | `/api/videos/{video_id}/metrics` | Read metric history |

Video statuses are `draft`, `scheduled`, `published`, and `failed`.
`platform_video_id` is nullable. Any `published_at` must have a timezone.
Video filters are `channel_id`, `status`, `limit`, and `offset`.

Metric counts must be non-negative. `click_through_rate` is a decimal ratio from
`0` through `1`. Omitted values remain `null`; the API never converts an
unavailable platform measurement to zero. History supports `order=newest` or
`order=oldest`.

Shared snapshots can also include unique and engaged viewers, completed views,
saves, views from impressions, follower gains/losses, new/returning viewers, and
first-hour performance fields.

Structured analytics are submitted with the snapshot:

```json
{
  "views": 1000,
  "likes": 100,
  "comments": 20,
  "shares": 30,
  "saves": 50,
  "retention_points": [
    {
      "position_ratio": "0.500000",
      "audience_retention_ratio": "0.700000"
    }
  ],
  "traffic_sources": [
    {
      "source_type": "browse_features",
      "views": 500,
      "percentage": "0.500000"
    }
  ],
  "geography": [
    {
      "country_code": "DE",
      "viewers": 300,
      "percentage": "0.333333"
    }
  ],
  "discovery_assets": [
    {
      "asset_type": "hashtag",
      "asset_value": "#creatoros",
      "views": 100
    }
  ],
  "youtube_extension": {
    "suggested_video_views": 200,
    "reported_impressions_ctr": "0.400000"
  }
}
```

The accepted discovery asset types are `hashtag`, `sound`, `search_term`,
`external_referrer`, and `other`. A request may contain only the TikTok,
Instagram, or YouTube extension matching the video's channel platform.

Responses derive engagement, follower conversion, share, save, new/returning
viewer, impressions-to-view, average-percentage-viewed, and completion rates.
A derived rate is `null` when required inputs or a nonzero denominator are
unavailable. Derived values are not persisted, so they cannot become stale.

## Errors

- `401`: missing, invalid, expired, revoked, or disabled-user session
- `403`: CSRF failure, missing workspace membership, or insufficient role
- `404`: resource absent from the active workspace
- `409`: uniqueness conflict
- `422`: invalid request data
- `429`: login throttle active

Raw database exceptions and credential-enumeration details are not returned.
