# Instagram integration setup

CreatorOS uses the Instagram API with Instagram Login for professional
Business and Creator accounts. It does not use the older Facebook Page-linked
login flow.

This guide was checked against Meta's official Instagram API Postman workspace
on July 29, 2026:

- [Official Instagram API workspace](https://www.postman.com/meta/instagram/overview)
- [Instagram API with Instagram Login](https://www.postman.com/meta/instagram/folder/23987686-98bfade9-3736-4738-8b4a-f56d6534f6de)
- [Insights guide](https://www.postman.com/meta/instagram/folder/23987686-f659d7d1-d74c-44e4-9192-9b1e8694c511)
- [Content publishing guide](https://www.postman.com/meta/instagram/folder/23987686-bc459e67-42aa-4ea0-ad25-e5a6e42c3a83)

Meta changes permissions, metrics, review rules, and supported API versions.
Recheck those sources before enabling a production connection.

## Eligibility and access

- The account must be an Instagram professional Business or Creator account.
- Consumer/personal accounts are not supported.
- Instagram Login does not require the account to be linked to a Facebook Page.
- This login path does not expose ads or tagging.
- Standard Access is suitable only for professional accounts owned or managed
  by the app owner and added in the App Dashboard.
- Advanced Access and Meta App Review are required before serving professional
  accounts the app owner does not own or manage.

## Meta app configuration

1. Create a Meta app suitable for business integrations.
2. Add the Instagram API product and choose Business Login for Instagram.
3. Add this exact local OAuth redirect URI:

   ```text
   http://127.0.0.1:8000/api/integrations/instagram/oauth/callback
   ```

4. For production, register an HTTPS redirect URI on the production origin.
5. Configure Meta's required privacy-policy, terms, data-deletion, and
   deauthorization callback information before App Review.
6. Request only the features and permissions CreatorOS actually uses.

## CreatorOS configuration

Copy the safe variable names from `.env.example` and set real values only in
the local, ignored `.env` file or a production secret manager:

```text
INSTAGRAM_APP_ID=
INSTAGRAM_APP_SECRET=
INSTAGRAM_OAUTH_REDIRECT_URI=http://127.0.0.1:8000/api/integrations/instagram/oauth/callback
INSTAGRAM_API_VERSION=v23.0
INSTAGRAM_ENABLE_PUBLISHING=false
INSTAGRAM_HTTP_TIMEOUT_SECONDS=30
```

`v23.0` is a configurable supported version represented in Meta's current
official collection. Upgrade it deliberately after reviewing Meta's changelog
and rerunning the adapter tests.

## Permission policy

CreatorOS requests these minimum synchronization permissions:

- `instagram_business_basic`
- `instagram_business_manage_insights`

It requests `instagram_business_content_publish` only when both the server
setting and the individual OAuth request enable publishing. Messaging and
comment-management permissions are outside this sprint.

OAuth state is random, stored only as a hash, bound to one CreatorOS user and
workspace, expires quickly, and can be consumed once. The Meta app secret,
authorization code, and access tokens are never stored in PostgreSQL or logs.

## Supported synchronization

- Professional-account identity, username, type, follower count, and media
  count mapping.
- Cursor-paginated owned media synchronization.
- Media insights including officially returned views, reach, likes, comments,
  shares, saves, interactions, and Reels watch-time metrics.
- Daily account insight snapshots for reach, profile views, followers,
  accounts engaged, interactions, follows, and unfollows when Meta returns
  them.
- Empty or unavailable Meta insight data remains null/unavailable and is never
  converted to zero.

The targeted API exposes total media reach but does not provide dependable
per-media Reels-tab, Feed, Explore, and profile reach breakdowns. CreatorOS
therefore keeps those fields null. It does not infer them from media type,
permalink, or total reach.

## Publishing boundary

Meta officially supports image, video, Reel, and carousel publishing through
media containers. The current adapter implements single image, video, and Reel
container creation, container status, final publication, and publishing-limit
inspection. Carousel orchestration is deferred.

Important constraints:

- Media passed by URL must be on a publicly accessible HTTPS server while Meta
  fetches it.
- CreatorOS rejects localhost, private-address, credential-bearing, and
  non-HTTPS media URLs.
- Meta's current guide states a limit of 100 API-published posts per rolling
  24-hour period and exposes `/content_publishing_limit`.
- Container states are `IN_PROGRESS`, `FINISHED`, `PUBLISHED`, `ERROR`, or
  `EXPIRED`. Meta recommends polling once per minute for no more than five
  minutes.
- A `FINISHED` container is ready for the separate `/media_publish` call.
- Server-side scheduling is performed by CreatorOS at the scheduled time; Meta
  does not receive a CreatorOS schedule timestamp.

Runtime publication remains disabled until Sprint U supplies an authorized
media-storage boundary and Sprint R connects it to the approved publishing
worker. Tests use fakes only and never contact Meta or publish content.

## Disconnect and rollback

Disconnect requests revoke the granted Instagram permissions through Meta,
mark the connection disconnected, and delete the local credential reference.
Expired/revoked credentials are treated as already unavailable; CreatorOS
still removes its local secret.

Migration `0010` only adds append-only account insight snapshots. Before any
rollback, stop workers and verify no snapshots must be retained. The downgrade
deletes that table and is destructive to its stored insight history:

```powershell
.\venv\Scripts\alembic.exe downgrade 0009
```
