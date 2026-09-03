from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.jobs import (
    AnalyticsWorkerDependencies,
    JobRegistry,
    register_analytics_jobs,
    run_once,
)
from app.models.analytics_sync import AnalyticsSyncRun
from app.models.channel import Channel, Platform
from app.models.durable_job import DurableJob
from app.models.platform_integration import PlatformSyncCursor
from app.models.publishing import ActivityEvent
from app.models.video_metric import VideoMetric
from app.platforms import (
    AdapterPage,
    CredentialMaterial,
    PlatformRateLimitError,
    RemoteMetricSnapshot,
    RemoteVideo,
)
from app.services import analytics_sync_service
from tests.test_core_apis import headers, register
from tests.test_platform_adapters import (
    FakeAdapter,
    FakeCredentialStore,
    create_connection,
)

CAPTURED_AT = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)


class AnalyticsAdapter(FakeAdapter):
    def list_videos(
        self,
        external_channel_id: str,
        credentials: CredentialMaterial,
        *,
        cursor: str | None = None,
    ) -> AdapterPage[RemoteVideo]:
        del credentials
        if cursor == "videos-complete":
            return AdapterPage(items=(), next_cursor=None)
        return AdapterPage(
            items=(
                RemoteVideo(
                    external_video_id="video-1",
                    external_channel_id=external_channel_id,
                    title="Analytics video",
                    published_at=CAPTURED_AT,
                ),
            ),
            next_cursor="videos-complete",
        )

    def sync_metrics(
        self,
        external_video_id: str,
        credentials: CredentialMaterial,
        *,
        cursor: str | None = None,
    ) -> AdapterPage[RemoteMetricSnapshot]:
        del credentials
        if cursor == "metrics-complete":
            return AdapterPage(items=(), next_cursor=None)
        return AdapterPage(
            items=(
                RemoteMetricSnapshot(
                    external_video_id=external_video_id,
                    captured_at=CAPTURED_AT,
                    values={"views": 150, "likes": 12},
                    unavailable_fields=("shares",),
                    metadata={
                        "retention_points": [
                            {
                                "position_ratio": "0.5",
                                "audience_retention_ratio": "0.7",
                            }
                        ],
                        "traffic_sources": [{"source_type": "search", "views": 100}],
                    },
                ),
            ),
            next_cursor="metrics-complete",
        )


class RateLimitedAdapter(AnalyticsAdapter):
    def sync_channel(self, external_channel_id, credentials):
        del external_channel_id, credentials
        raise PlatformRateLimitError(
            "provider_rate_limit",
            "Provider detail must not escape",
            retry_after_seconds=60,
        )


class MetricRateLimitedAdapter(AnalyticsAdapter):
    def sync_metrics(
        self,
        external_video_id,
        credentials,
        *,
        cursor=None,
    ):
        del external_video_id, credentials, cursor
        raise PlatformRateLimitError(
            "provider_rate_limit",
            "Provider detail must not escape",
            retry_after_seconds=60,
        )


class InstagramAnalyticsAdapter(AnalyticsAdapter):
    platform = Platform.INSTAGRAM


class TikTokAnalyticsAdapter(AnalyticsAdapter):
    platform = Platform.TIKTOK


def _dependencies(
    store: FakeCredentialStore,
    adapter: FakeAdapter,
) -> AnalyticsWorkerDependencies:
    def factory(quota_recorder=None, request_recorder=None):
        del quota_recorder, request_recorder
        return adapter

    factories = {
        Platform.YOUTUBE: {"youtube_adapter_factory": factory},
        Platform.INSTAGRAM: {"instagram_adapter_factory": factory},
        Platform.TIKTOK: {"tiktok_adapter_factory": factory},
    }
    return AnalyticsWorkerDependencies(
        secret_store=store, **factories[adapter.platform]
    )


def _connected_account(
    client: TestClient,
    db: Session,
    *,
    email: str,
) -> tuple[dict, object, FakeCredentialStore]:
    auth = register(client, email)
    connection = create_connection(db, auth)
    store = FakeCredentialStore()
    store.values[connection.credential_reference] = CredentialMaterial(
        access_token=SecretStr("local-test-token")
    )
    return auth, connection, store


def test_schedule_route_is_idempotent_and_workspace_scoped(
    client: TestClient,
    db_session: Session,
) -> None:
    auth, connection, _ = _connected_account(
        client,
        db_session,
        email="analytics-schedule@example.com",
    )
    request_headers = {
        **headers(auth, write=True),
        "Idempotency-Key": "analytics-schedule-1",
    }
    first = client.post(
        "/api/analytics-sync/schedule",
        headers=request_headers,
        json={"connection_ids": [str(connection.id)]},
    )
    repeated = client.post(
        "/api/analytics-sync/schedule",
        headers=request_headers,
        json={"connection_ids": [str(connection.id)]},
    )

    assert first.status_code == 202
    assert repeated.status_code == 202
    assert repeated.json()[0]["id"] == first.json()[0]["id"]
    assert db_session.scalar(select(func.count(AnalyticsSyncRun.id))) == 1
    assert db_session.scalar(select(func.count(DurableJob.id))) == 1

    other = register(client, "analytics-other@example.com")
    hidden = client.get(
        f"/api/analytics-sync/runs/{first.json()[0]['id']}",
        headers=headers(other),
    )
    assert hidden.status_code == 404


def test_worker_syncs_and_deduplicates_analytics(
    client: TestClient,
    db_session: Session,
) -> None:
    auth, connection, store = _connected_account(
        client,
        db_session,
        email="analytics-worker@example.com",
    )
    workspace_id = UUID(auth["workspace_id"])
    adapter = AnalyticsAdapter()

    first_run = analytics_sync_service.schedule_sync_runs(
        db_session,
        workspace_id=workspace_id,
        requested_by_user_id=UUID(auth["user"]["id"]),
        idempotency_key="analytics-worker-first",
        connection_ids=(connection.id,),
    )[0]
    registry = JobRegistry()
    register_analytics_jobs(
        registry,
        db_session,
        dependencies=_dependencies(store, adapter),
    )
    completed = run_once(
        db_session,
        registry=registry,
        worker_id="analytics-worker-1",
    )

    assert completed is not None
    assert completed.status == "succeeded"
    db_session.refresh(first_run)
    assert first_run.status == "succeeded"
    assert first_run.channels_synced == 1
    assert first_run.videos_synced == 1
    assert first_run.metrics_synced == 1
    assert db_session.scalar(select(func.count(VideoMetric.id))) == 1
    assert (
        db_session.scalar(
            select(PlatformSyncCursor).where(
                PlatformSyncCursor.connection_id == connection.id,
                PlatformSyncCursor.resource_type == "videos",
            )
        ).cursor
        == "videos-complete"
    )

    second_run = analytics_sync_service.schedule_sync_runs(
        db_session,
        workspace_id=workspace_id,
        requested_by_user_id=UUID(auth["user"]["id"]),
        idempotency_key="analytics-worker-second",
        connection_ids=(connection.id,),
    )[0]
    second = run_once(
        db_session,
        registry=registry,
        worker_id="analytics-worker-1",
    )
    assert second is not None
    assert second.status == "succeeded"
    db_session.refresh(second_run)
    assert db_session.scalar(select(func.count(VideoMetric.id))) == 1

    health = client.get(
        "/api/analytics-sync/health",
        headers=headers(auth),
    )
    assert health.status_code == 200
    assert health.json()[0]["healthy"] is True
    assert health.json()[0]["latest_run"]["id"] == str(second_run.id)


@pytest.mark.parametrize(
    ("platform", "adapter_type"),
    [
        (Platform.INSTAGRAM, InstagramAnalyticsAdapter),
        (Platform.TIKTOK, TikTokAnalyticsAdapter),
    ],
)
def test_worker_dispatches_account_analytics_for_each_supported_platform(
    client: TestClient,
    db_session: Session,
    platform: Platform,
    adapter_type: type[AnalyticsAdapter],
) -> None:
    auth = register(client, f"analytics-{platform.value}@example.com")
    connection = create_connection(
        db_session,
        auth,
        platform=platform,
        account_id=f"{platform.value}-account",
    )
    store = FakeCredentialStore()
    store.values[connection.credential_reference] = CredentialMaterial(
        access_token=SecretStr("local-test-token")
    )
    run = analytics_sync_service.schedule_sync_runs(
        db_session,
        workspace_id=UUID(auth["workspace_id"]),
        requested_by_user_id=UUID(auth["user"]["id"]),
        idempotency_key=f"analytics-{platform.value}",
        connection_ids=(connection.id,),
    )[0]
    registry = JobRegistry()
    register_analytics_jobs(
        registry,
        db_session,
        dependencies=_dependencies(store, adapter_type()),
    )

    completed = run_once(
        db_session,
        registry=registry,
        worker_id=f"analytics-worker-{platform.value}",
    )

    assert completed is not None
    assert completed.status == "succeeded"
    db_session.refresh(run)
    assert run.status == "succeeded"
    assert run.channels_synced == 1
    assert run.videos_synced == 1
    assert run.metrics_synced == 1
    assert run.account_metrics_synced == 1


def test_inactive_channel_is_skipped_without_provider_call(
    client: TestClient,
    db_session: Session,
) -> None:
    auth, connection, store = _connected_account(
        client,
        db_session,
        email="analytics-inactive@example.com",
    )
    channel = Channel(
        user_id=UUID(auth["user"]["id"]),
        workspace_id=UUID(auth["workspace_id"]),
        platform=Platform.YOUTUBE.value,
        platform_channel_id=connection.external_account_id,
        name="Inactive",
        is_active=False,
    )
    db_session.add(channel)
    db_session.commit()
    run = analytics_sync_service.schedule_sync_runs(
        db_session,
        workspace_id=UUID(auth["workspace_id"]),
        requested_by_user_id=UUID(auth["user"]["id"]),
        idempotency_key="analytics-inactive",
        connection_ids=(connection.id,),
    )[0]
    registry = JobRegistry()
    register_analytics_jobs(
        registry,
        db_session,
        dependencies=_dependencies(store, RateLimitedAdapter()),
    )

    completed = run_once(
        db_session,
        registry=registry,
        worker_id="analytics-worker-inactive",
    )

    assert completed is not None
    assert completed.status == "succeeded"
    db_session.refresh(run)
    assert run.status == "skipped"
    assert run.summary["reason"] == "channel_inactive"


def test_rate_limit_schedules_safe_retry_and_records_activity(
    client: TestClient,
    db_session: Session,
) -> None:
    auth, connection, store = _connected_account(
        client,
        db_session,
        email="analytics-rate-limit@example.com",
    )
    run = analytics_sync_service.schedule_sync_runs(
        db_session,
        workspace_id=UUID(auth["workspace_id"]),
        requested_by_user_id=UUID(auth["user"]["id"]),
        idempotency_key="analytics-rate-limit",
        connection_ids=(connection.id,),
        max_attempts=2,
    )[0]
    registry = JobRegistry()
    register_analytics_jobs(
        registry,
        db_session,
        dependencies=_dependencies(store, RateLimitedAdapter()),
    )

    retried = run_once(
        db_session,
        registry=registry,
        worker_id="analytics-worker-rate-limit",
    )

    assert retried is not None
    assert retried.status == "retry_scheduled"
    assert retried.last_error_code == "analytics_rate_limited"
    assert "Provider detail" not in (retried.last_error_message or "")
    db_session.refresh(run)
    assert run.status == "retry_scheduled"
    assert run.last_error_message == "Analytics synchronization was rate limited"
    event_types = set(db_session.scalars(select(ActivityEvent.event_type)).all())
    assert "analytics_sync_scheduled" in event_types
    assert "analytics_sync_retry_scheduled" in event_types


def test_failed_metric_sync_does_not_advance_its_cursor(
    client: TestClient,
    db_session: Session,
) -> None:
    auth, connection, store = _connected_account(
        client,
        db_session,
        email="analytics-metric-rate-limit@example.com",
    )
    run = analytics_sync_service.schedule_sync_runs(
        db_session,
        workspace_id=UUID(auth["workspace_id"]),
        requested_by_user_id=UUID(auth["user"]["id"]),
        idempotency_key="analytics-metric-rate-limit",
        connection_ids=(connection.id,),
        max_attempts=2,
    )[0]
    registry = JobRegistry()
    register_analytics_jobs(
        registry,
        db_session,
        dependencies=_dependencies(store, MetricRateLimitedAdapter()),
    )

    retried = run_once(
        db_session,
        registry=registry,
        worker_id="analytics-worker-metric-rate-limit",
    )

    assert retried is not None
    assert retried.status == "retry_scheduled"
    db_session.refresh(run)
    assert run.status == "retry_scheduled"
    cursor_types = set(
        db_session.scalars(
            select(PlatformSyncCursor.resource_type).where(
                PlatformSyncCursor.connection_id == connection.id
            )
        ).all()
    )
    assert "videos" in cursor_types
    assert "metrics.video-1" not in cursor_types
