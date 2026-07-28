from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from tests.test_core_apis import (
    create_channel,
    create_video,
    headers,
    register,
)


def test_structured_analytics_and_derived_rates(client: TestClient) -> None:
    auth = register(client)
    channel = create_channel(client, auth)
    video = create_video(
        client,
        auth,
        channel["id"],
        duration_seconds=40,
    )

    response = client.post(
        f"/api/videos/{video['id']}/metrics",
        headers=headers(auth, write=True),
        json={
            "views": 1000,
            "unique_viewers": 900,
            "engaged_views": 500,
            "completed_views": 400,
            "likes": 100,
            "comments": 20,
            "shares": 30,
            "saves": 50,
            "impressions": 2000,
            "views_from_impressions": 800,
            "watch_time_seconds": 20000,
            "average_view_duration_seconds": 20,
            "followers_gained": 10,
            "followers_lost": 2,
            "new_viewers": 600,
            "returning_viewers": 300,
            "first_hour_views": 250,
            "first_hour_likes": 25,
            "retention_points": [
                {
                    "position_ratio": "0.500000",
                    "audience_retention_ratio": "0.700000",
                }
            ],
            "traffic_sources": [
                {
                    "source_type": "Browse_Features",
                    "views": 500,
                    "percentage": "0.500000",
                }
            ],
            "demographics": [
                {
                    "dimension": "AGE",
                    "segment": "18-24",
                    "percentage": "0.400000",
                }
            ],
            "geography": [
                {
                    "country_code": "de",
                    "viewers": 300,
                    "percentage": "0.333333",
                }
            ],
            "discovery_assets": [
                {
                    "asset_type": "hashtag",
                    "asset_value": "#creator",
                    "views": 100,
                }
            ],
            "youtube_extension": {
                "suggested_video_views": 200,
                "browse_feature_views": 500,
                "subscriber_views": 250,
                "unsubscribed_views": 750,
                "reported_impressions_ctr": "0.400000",
            },
        },
    )

    assert response.status_code == 201
    metric = response.json()
    assert Decimal(metric["engagement_rate"]) == Decimal("0.200000")
    assert Decimal(metric["follower_conversion_rate"]) == Decimal("0.010000")
    assert Decimal(metric["share_rate"]) == Decimal("0.030000")
    assert Decimal(metric["save_rate"]) == Decimal("0.050000")
    assert Decimal(metric["new_viewer_ratio"]) == Decimal("0.666667")
    assert Decimal(metric["returning_viewer_ratio"]) == Decimal("0.333333")
    assert Decimal(metric["impressions_to_view_rate"]) == Decimal("0.400000")
    assert Decimal(metric["average_percentage_viewed"]) == Decimal("0.500000")
    assert Decimal(metric["completion_rate"]) == Decimal("0.400000")
    assert metric["traffic_sources"][0]["source_type"] == "browse_features"
    assert metric["demographics"][0]["dimension"] == "age"
    assert metric["geography"][0]["country_code"] == "DE"
    assert metric["youtube_extension"]["suggested_video_views"] == 200

    history = client.get(
        f"/api/videos/{video['id']}/metrics",
        headers=headers(auth),
    )
    assert history.status_code == 200
    assert history.json()[0]["retention_points"][0][
        "audience_retention_ratio"
    ] == "0.700000"


def test_unavailable_metrics_remain_null(client: TestClient) -> None:
    auth = register(client)
    channel = create_channel(client, auth)
    video = create_video(client, auth, channel["id"])

    response = client.post(
        f"/api/videos/{video['id']}/metrics",
        headers=headers(auth, write=True),
        json={"views": 0},
    )

    assert response.status_code == 201
    metric = response.json()
    assert metric["views"] == 0
    assert metric["likes"] is None
    assert metric["saves"] is None
    assert metric["unique_viewers"] is None
    assert metric["engagement_rate"] is None
    assert metric["completion_rate"] is None
    assert metric["average_percentage_viewed"] is None


@pytest.mark.parametrize(
    ("platform", "extension_name", "extension_payload", "expected_field"),
    [
        (
            "tiktok",
            "tiktok_extension",
            {"for_you_views": 80, "sound_views": 20},
            "for_you_views",
        ),
        (
            "instagram",
            "instagram_extension",
            {"reels_tab_reach": 75, "accounts_engaged": 25},
            "reels_tab_reach",
        ),
    ],
)
def test_platform_extensions_match_video_platform(
    client: TestClient,
    platform: str,
    extension_name: str,
    extension_payload: dict[str, int],
    expected_field: str,
) -> None:
    auth = register(client)
    channel = create_channel(
        client,
        auth,
        platform=platform,
        platform_channel_id=f"{platform}-channel",
    )
    video = create_video(client, auth, channel["id"])

    response = client.post(
        f"/api/videos/{video['id']}/metrics",
        headers=headers(auth, write=True),
        json={extension_name: extension_payload},
    )

    assert response.status_code == 201
    assert response.json()[extension_name][expected_field] is not None


def test_wrong_or_multiple_platform_extensions_are_rejected(
    client: TestClient,
) -> None:
    auth = register(client)
    channel = create_channel(client, auth)
    video = create_video(client, auth, channel["id"])
    endpoint = f"/api/videos/{video['id']}/metrics"

    wrong = client.post(
        endpoint,
        headers=headers(auth, write=True),
        json={"tiktok_extension": {"for_you_views": 10}},
    )
    multiple = client.post(
        endpoint,
        headers=headers(auth, write=True),
        json={
            "youtube_extension": {"search_views": 10},
            "tiktok_extension": {"search_views": 10},
        },
    )

    assert wrong.status_code == 422
    assert wrong.json() == {"detail": "tiktok analytics require a tiktok video"}
    assert multiple.status_code == 422


def test_duplicate_and_invalid_structured_analytics_are_rejected(
    client: TestClient,
) -> None:
    auth = register(client)
    channel = create_channel(client, auth)
    video = create_video(client, auth, channel["id"])
    endpoint = f"/api/videos/{video['id']}/metrics"

    duplicate = client.post(
        endpoint,
        headers=headers(auth, write=True),
        json={
            "retention_points": [
                {
                    "position_ratio": "0.5",
                    "audience_retention_ratio": "0.8",
                },
                {
                    "position_ratio": "0.5",
                    "audience_retention_ratio": "0.7",
                },
            ]
        },
    )
    invalid = client.post(
        endpoint,
        headers=headers(auth, write=True),
        json={
            "traffic_sources": [
                {
                    "source_type": "search",
                    "percentage": "1.1",
                }
            ]
        },
    )

    assert duplicate.status_code == 422
    assert invalid.status_code == 422
