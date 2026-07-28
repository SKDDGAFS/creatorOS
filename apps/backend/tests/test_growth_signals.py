from decimal import Decimal

from fastapi.testclient import TestClient

from tests.test_core_apis import headers, register


def profile_payload(name: str = "Short-form growth") -> dict:
    return {
        "name": name,
        "platform": "youtube",
        "content_format": "short",
        "account_size_min": 0,
        "account_size_max": 10000,
        "video_duration_min_seconds": 10,
        "video_duration_max_seconds": 60,
        "goal": "subscriber_growth",
        "evidence_min": 10,
        "evidence_max": 10000,
        "weights": [
            {
                "signal": "completion_rate",
                "tier": "strong",
                "weight": "2.000000",
                "minimum_sample_size": 100,
                "full_confidence_sample_size": 1000,
            },
            {
                "signal": "raw_views",
                "tier": "contextual",
                "weight": "1.000000",
                "minimum_sample_size": 10,
                "full_confidence_sample_size": 100,
            },
        ],
    }


def create_profile(
    client: TestClient,
    auth: dict,
    name: str = "Short-form growth",
) -> dict:
    response = client.post(
        "/api/growth-signals/profiles",
        headers=headers(auth, write=True),
        json=profile_payload(name),
    )
    assert response.status_code == 201
    return response.json()


def test_signal_catalog_preserves_advisory_tiers(client: TestClient) -> None:
    register(client)
    response = client.get("/api/growth-signals/catalog")

    assert response.status_code == 200
    catalog = {
        item["signal"]: item["suggested_tier"]
        for item in response.json()
    }
    assert catalog["retention_curve"] == "strong"
    assert catalog["save_rate"] == "medium"
    assert catalog["raw_views"] == "contextual"


def test_profiles_are_contextual_versioned_and_workspace_owned(
    client: TestClient,
) -> None:
    auth = register(client)
    first = create_profile(client, auth)
    second = create_profile(client, auth)
    listed = client.get(
        "/api/growth-signals/profiles",
        headers=headers(auth),
    )

    assert first["version"] == 1
    assert second["version"] == 2
    assert second["workspace_id"] == auth["workspace_id"]
    assert second["created_by_user_id"] == auth["user"]["id"]
    assert second["content_format"] == "short"
    assert [item["version"] for item in listed.json()] == [2, 1]


def test_scoring_applies_sample_and_source_confidence(
    client: TestClient,
) -> None:
    auth = register(client)
    profile = create_profile(client, auth)
    response = client.post(
        f"/api/growth-signals/profiles/{profile['id']}/score",
        headers=headers(auth),
        json={
            "evidence_volume": 500,
            "observations": [
                {
                    "signal": "completion_rate",
                    "value": "0.800000",
                    "sample_size": 500,
                    "source_confidence": "0.800000",
                },
                {
                    "signal": "raw_views",
                    "value": "1.000000",
                    "sample_size": 5,
                    "source_confidence": "1.000000",
                },
            ],
        },
    )

    assert response.status_code == 200
    score = response.json()
    assert Decimal(score["score"]) == Decimal("0.213333")
    assert Decimal(score["confidence"]) == Decimal("0.266667")
    assert Decimal(score["coverage"]) == Decimal("1.000000")
    assert score["contributions"][0]["sample_confidence"] == "0.500000"
    assert "correlational" not in score["interpretation"]
    assert score["interpretation"].startswith("Low-confidence")


def test_missing_signal_reduces_coverage_not_available_values(
    client: TestClient,
) -> None:
    auth = register(client)
    profile = create_profile(client, auth)
    response = client.post(
        f"/api/growth-signals/profiles/{profile['id']}/score",
        headers=headers(auth),
        json={
            "evidence_volume": 500,
            "observations": [
                {
                    "signal": "completion_rate",
                    "value": "0.800000",
                    "sample_size": 1000,
                }
            ],
        },
    )

    assert response.status_code == 200
    assert Decimal(response.json()["score"]) == Decimal("0.533333")
    assert Decimal(response.json()["confidence"]) == Decimal("0.666667")
    assert Decimal(response.json()["coverage"]) == Decimal("0.666667")


def test_profile_evidence_range_and_validation_are_enforced(
    client: TestClient,
) -> None:
    auth = register(client)
    profile = create_profile(client, auth)
    outside = client.post(
        f"/api/growth-signals/profiles/{profile['id']}/score",
        headers=headers(auth),
        json={
            "evidence_volume": 5,
            "observations": [
                {
                    "signal": "completion_rate",
                    "value": "0.5",
                    "sample_size": 100,
                }
            ],
        },
    )
    invalid = profile_payload("Invalid")
    invalid["weights"].append(invalid["weights"][0])
    duplicate = client.post(
        "/api/growth-signals/profiles",
        headers=headers(auth, write=True),
        json=invalid,
    )

    assert outside.status_code == 422
    assert duplicate.status_code == 422


def test_workspace_isolation_and_deactivation(
    client: TestClient,
) -> None:
    first = register(client, "first-growth@example.com")
    profile = create_profile(client, first)
    client.cookies.clear()
    second = register(client, "second-growth@example.com")
    hidden = client.get(
        f"/api/growth-signals/profiles/{profile['id']}",
        headers=headers(second),
    )
    assert hidden.status_code == 404

    client.cookies.clear()
    login = client.post(
        "/api/auth/login",
        json={
            "email": "first-growth@example.com",
            "password": "correct horse battery staple",
        },
    )
    first["csrf"] = login.json()["csrf_token"]
    deactivated = client.post(
        f"/api/growth-signals/profiles/{profile['id']}/deactivate",
        headers=headers(first, write=True),
    )
    blocked = client.post(
        f"/api/growth-signals/profiles/{profile['id']}/score",
        headers=headers(first),
        json={
            "evidence_volume": 500,
            "observations": [
                {
                    "signal": "completion_rate",
                    "value": "0.5",
                    "sample_size": 100,
                }
            ],
        },
    )

    assert deactivated.status_code == 200
    assert not deactivated.json()["is_active"]
    assert blocked.status_code == 422
