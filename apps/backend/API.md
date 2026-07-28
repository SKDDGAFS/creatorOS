# CreatorOS core API

The local API defaults to `http://127.0.0.1:8000`. Interactive OpenAPI
documentation is available at `/docs`.

## Channels

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/channels` | Create a channel for an existing user |
| `GET` | `/api/channels` | List and filter channels |
| `GET` | `/api/channels/{channel_id}` | Get one channel |
| `PATCH` | `/api/channels/{channel_id}` | Partially update one channel |

Create request:

```json
{
  "user_id": "11111111-1111-1111-1111-111111111111",
  "platform": "youtube",
  "platform_channel_id": "UC-example",
  "name": "CreatorOS",
  "handle": "@creatoros",
  "is_active": true
}
```

The `user_id` must already exist in the `users` table. Supported platforms are
`youtube`, `tiktok`, and `instagram`.

List filters:

```text
GET /api/channels?user_id={uuid}&platform=youtube&is_active=true&limit=20&offset=0
```

## Videos

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/videos` | Create a video for an existing channel |
| `GET` | `/api/videos` | List and filter videos |
| `GET` | `/api/videos/{video_id}` | Get one video |
| `PATCH` | `/api/videos/{video_id}` | Partially update one video |

Create request:

```json
{
  "channel_id": "22222222-2222-2222-2222-222222222222",
  "platform_video_id": null,
  "title": "My next video",
  "description": "Draft description",
  "status": "draft",
  "published_at": null
}
```

Supported statuses are `draft`, `scheduled`, `published`, and `failed`.
`platform_video_id` can remain null until an external platform assigns one.
Any supplied `published_at` must contain a timezone offset.

List filters:

```text
GET /api/videos?channel_id={uuid}&status=published&limit=20&offset=0
```

## Metric snapshots

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/videos/{video_id}/metrics` | Append a metric snapshot |
| `GET` | `/api/videos/{video_id}/metrics` | Read metric history |

Create request:

```json
{
  "captured_at": "2026-07-28T12:00:00+00:00",
  "views": 1250,
  "likes": 110,
  "comments": 12,
  "shares": 8,
  "watch_time_seconds": 48000,
  "average_view_duration_seconds": 38,
  "impressions": 9000,
  "click_through_rate": "0.0750"
}
```

All count and duration fields must be non-negative. Click-through rate uses a
decimal ratio from `0` through `1`; `0.0750` means 7.5%. Every POST creates a
new historical row.

History is newest-first by default:

```text
GET /api/videos/{video_id}/metrics?order=newest&limit=100&offset=0
GET /api/videos/{video_id}/metrics?order=oldest&limit=100&offset=0
```

## Pagination and errors

`limit` must be between 1 and 100. `offset` must be zero or greater. Results use
stable timestamp-and-UUID ordering.

Missing records return:

```json
{"detail": "Channel not found"}
```

Uniqueness conflicts return HTTP `409` with a safe explanation. Pydantic input
validation returns HTTP `422`. Raw database exceptions are never returned.

## Local commands

Apply migrations:

```powershell
.\venv\Scripts\alembic.exe upgrade head
```

Run the API:

```powershell
.\venv\Scripts\uvicorn.exe main:app --reload
```

Run all tests:

```powershell
.\venv\Scripts\python.exe -m pytest -q
```
