# Scheduling foundation

CreatorOS is a private single-user tool. Analytics exist to help scheduling.
This sprint preserves history and creates the interface foundation.

## Model decision

The local queue is now persistent. `Video` retains its channel, title,
description, status, published timestamp, and now a relative local media
reference. `ScheduledPost` is separate from the video lifecycle, so cancelling
a post preserves content and metric history. Do not repurpose `published_at` as
a scheduling timestamp.

The additive `0003` migration introduces one `ScheduledPost` record with:

| Field                   | Purpose                                                             |
| ----------------------- | ------------------------------------------------------------------- |
| id                      | UUID                                                                |
| video_id                | Restrictive foreign key to content/video                            |
| channel_id              | Restrictive foreign key to target channel; derive platform          |
| scheduled_at            | Aware UTC timestamp, nullable while draft                           |
| recommended_at          | Nullable aware UTC timestamp; no fabricated default                 |
| status                  | Draft, scheduled, cancelled initially; publishing states come later |
| metadata                | Validated platform-specific JSON payload                            |
| created_at / updated_at | Aware UTC timestamps                                                |

The target channel is still explicit even though the current `Video` is bound to
one channel. The service rejects mismatched video/channel pairs. Local bootstrap
creates one un-authorized preparation channel per supported platform; this is a
local target record, not an OAuth connection.

Uploads accept MP4, MOV, WebM, and AVI under the configured size limit. Files are
stored below `STORAGE_PATH/videos` with UUID names and are never overwritten.
Failed writes remove partial files. The API stores an IANA timezone for editing
and persists the actual instant in UTC. Clients must send an offset-aware instant;
ambiguous or nonexistent local wall-clock times must be resolved by the client
before submission rather than silently guessed.

Validate that video and target channel match while Video remains channel-bound.
Use an index on `(status, scheduled_at)`. Preserve content and metrics when a
post is cancelled. Store the chosen IANA timezone for editing and explain DST
ambiguities; persist actual instants in UTC. Do not start a worker in that sprint.

## Recommendation boundary

A future `recommendation_service.recommend(video_id, channel_id, now, timezone)`
returns either an aware suggested time with a method, sample count and reason,
or an explicit unavailable result with a reason. It must be read-only, must not
schedule anything itself, and must require the creator to accept or override it.
No executable stub is added before a caller exists.

Inputs come from Video.published_at, Channel.platform, and VideoMetric.captured_at,
views and engagement. Compare snapshots over equivalent post-publication windows;
do not compare lifetime views directly or treat a late snapshot as first-hour
performance. Content type and reliable first-hour samples are future inputs.
Define missing-versus-zero semantics before ingestion. Group by channel and local
day/time after timezone conversion. Sparse history must yield unavailable.
The first implementation should be a documented statistical baseline, without ML,
paid APIs, or synthetic predictions.

## Metadata boundary

A future `metadata_service.prepare(content, platform, format)` produces editable
drafts. It has no publishing or credential access and makes no paid API calls.

| Target        | Draft fields                           |
| ------------- | -------------------------------------- |
| YouTube video | title, description, tags               |
| YouTube Short | Shorts title, Shorts description, tags |
| Instagram     | caption, hashtags                      |
| TikTok        | caption, hashtags                      |

Validate fields separately per platform before storing ScheduledPost.metadata.
Keep creator approval and scheduling separate from generation. Actual platform
limits must be checked against official documentation during implementation.

## Platform credentials

Platform OAuth is separate from local CreatorOS access. A later connection
service will manage authorization, scopes, encrypted credentials, refresh and
revocation. Neither browser storage nor queue metadata may contain tokens. No
OAuth endpoints, credentials, platform SDKs, or publisher are added now.
