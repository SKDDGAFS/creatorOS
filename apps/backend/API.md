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

## Growth-signal profiles

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/growth-signals/catalog` | Read the advisory signal catalog |
| `POST` | `/api/growth-signals/profiles` | Create an immutable profile version |
| `GET` | `/api/growth-signals/profiles` | List active workspace profiles |
| `GET` | `/api/growth-signals/profiles/{id}` | Read one profile |
| `POST` | `/api/growth-signals/profiles/{id}/score` | Score normalized evidence |
| `POST` | `/api/growth-signals/profiles/{id}/deactivate` | Retire a profile |

Profiles scope configurable weights by platform, content format, account-size
range, video-duration range, goal, and evidence-volume range. Creating the same
profile name again creates a new version rather than changing historical
configuration.

Each weight stores a descriptive tier, positive configured weight, minimum sample
size, and full-confidence sample size. Suggested `strong`, `medium`, and
`contextual` tiers are guidance only; they do not assign a permanent weight.

Scoring accepts normalized values from zero through one, sample sizes, and
optional source confidence. The response reports:

- score: weighted value after confidence adjustment;
- confidence: weight-adjusted evidence confidence;
- coverage: the fraction of configured weight with an observation;
- per-signal contributions;
- an explicitly correlational interpretation.

Missing observations reduce coverage rather than being treated as zero. Samples
below a signal's configured minimum contribute zero confidence.

## Publishing workflow

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/publishing/jobs` | Create an idempotent publishing job |
| `GET` | `/api/publishing/jobs` | List or filter workspace jobs |
| `GET` | `/api/publishing/jobs/{id}` | Read one job and its audit history |
| `POST` | `/api/publishing/jobs/{id}/prepare` | Begin preparation or retry |
| `POST` | `/api/publishing/jobs/{id}/request-approval` | Request human approval |
| `GET` | `/api/publishing/approvals` | List pending approvals |
| `POST` | `/api/publishing/approvals/{id}/approve` | Approve as owner/admin |
| `POST` | `/api/publishing/approvals/{id}/reject` | Reject as owner/admin |
| `POST` | `/api/publishing/jobs/{id}/schedule` | Schedule approved content |
| `POST` | `/api/publishing/jobs/{id}/cancel` | Cancel a nonterminal job |
| `GET` | `/api/publishing/activity` | Read workspace activity |

Create requests require an opaque `Idempotency-Key` header containing 8 through
128 characters. Repeating a key with the same video returns the original job;
reusing it for another video returns `409`. Only a SHA-256 hash of the key is
stored.

The centralized state graph supports `draft`, `preparing`,
`awaiting_approval`, `approved`, `scheduled`, `publishing`, `published`,
`rejected`, `failed`, and `cancelled`. Routes never accept an arbitrary state.
Approval decisions require an owner or administrator. Scheduling and worker-side
publishing require a recorded human approval.

Every transition writes immutable transition and activity records in the same
database transaction as the state change. Rejected and failed jobs can return to
preparation; published and cancelled jobs are terminal. The worker-only service
methods record publishing, success, and safe failure state but do not call a
social platform.

## Durable jobs

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/jobs` | List/filter jobs in the active workspace |
| `GET` | `/api/jobs/{id}` | Read one job and its attempt history |
| `POST` | `/api/jobs/{id}/cancel` | Cancel as a workspace owner/admin |

Generic enqueueing is intentionally not exposed over HTTP. Domain services add
typed jobs internally, preventing clients from choosing arbitrary worker
operations or payloads. Payloads must be JSON objects and must never contain
credentials or secrets.

Jobs support `pending`, `running`, `retry_scheduled`, `succeeded`, `failed`, and
`cancelled` states. Priority ranges from 0 through 100. Eligible jobs are claimed
in descending priority order with PostgreSQL row locks and `SKIP LOCKED`, so
multiple workers cannot lease the same record.

Each lease has a worker owner and expiration time. Workers can extend it through
the internal heartbeat service. Retryable failures use capped exponential
backoff; exhausted or permanent failures become terminal. A recovery service
turns expired attempts into immutable `abandoned` history and safely reschedules
or fails the job. Only safe error codes/messages are persisted.

The typed handler registry executes one claimed job at a time and cannot run
shell commands. Platform and publishing workers will register domain-specific
handlers in later sprints.

## Platform adapter framework

The adapter framework is an internal service boundary in this sprint; it does
not expose OAuth or connection-write routes until concrete official providers
are implemented.

Every adapter implements typed methods for:

- connecting, refreshing, disconnecting, and revoking an account;
- listing and synchronizing channels and videos;
- synchronizing metric pages with explicit unavailable fields;
- validating approved publish requests;
- idempotent publishing and publish-status polling.

Credentials use Pydantic `SecretStr` values in memory and a `CredentialStore`
protocol at rest. PostgreSQL stores only a credential reference, safe account
metadata, scopes, and expiry. No access token, refresh token, authorization code,
client secret, or OAuth verifier belongs in a model or API response.

Provider pages carry opaque next cursors, which are persisted per connection and
resource type. Platform operations hash both the idempotency key and a canonical
request fingerprint, so a repeated key can return the original operation but
cannot silently represent another request.

Request logs retain only method, hostname, path, status, duration, outcome, safe
provider request ID, and recursively redacted structured metadata. URL query
strings and response bodies are never stored. Adapter errors distinguish
authentication, expiry, rate limiting, transient failure, permanent failure,
and unsupported capability.

## Errors

- `401`: missing, invalid, expired, revoked, or disabled-user session
- `403`: CSRF failure, missing workspace membership, or insufficient role
- `404`: resource absent from the active workspace
- `409`: uniqueness conflict
- `422`: invalid request data
- `429`: login throttle active

Raw database exceptions and credential-enumeration details are not returned.
