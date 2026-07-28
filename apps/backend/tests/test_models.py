from sqlalchemy import CheckConstraint, UniqueConstraint, Uuid

from app.db.base import Base
from app.models import (
    AuthSession,
    AuthThrottle,
    Channel,
    PasswordResetToken,
    User,
    Video,
    VideoMetric,
    Workspace,
    WorkspaceMembership,
)


def constraint_names(model: type) -> set[str | None]:
    return {constraint.name for constraint in model.__table__.constraints}


def test_all_domain_tables_are_registered() -> None:
    assert {
        "users",
        "workspaces",
        "workspace_memberships",
        "auth_sessions",
        "auth_throttles",
        "password_reset_tokens",
        "channels",
        "videos",
        "video_metrics",
    } <= set(Base.metadata.tables)


def test_models_use_uuid_primary_keys() -> None:
    for model in (
        User,
        Workspace,
        WorkspaceMembership,
        AuthSession,
        AuthThrottle,
        PasswordResetToken,
        Channel,
        Video,
        VideoMetric,
    ):
        id_column = model.__table__.c.id
        assert id_column.primary_key
        assert isinstance(id_column.type, Uuid)


def test_user_email_has_a_unique_index() -> None:
    email_indexes = [
        index
        for index in User.__table__.indexes
        if [column.name for column in index.columns] == ["email"]
    ]

    assert len(email_indexes) == 1
    assert email_indexes[0].unique


def test_channel_constraints_are_registered() -> None:
    assert "uq_channels_platform_platform_channel_id" in constraint_names(Channel)
    assert any(
        isinstance(constraint, CheckConstraint)
        and "youtube" in str(constraint.sqltext)
        for constraint in Channel.__table__.constraints
    )


def test_video_constraints_and_nullable_platform_id_are_registered() -> None:
    assert "uq_videos_channel_id_platform_video_id" in constraint_names(Video)
    assert Video.__table__.c.platform_video_id.nullable
    assert any(
        isinstance(constraint, CheckConstraint)
        and "scheduled" in str(constraint.sqltext)
        for constraint in Video.__table__.constraints
    )


def test_video_metric_history_index_supports_time_queries() -> None:
    metric_indexes = {
        index.name: [column.name for column in index.columns]
        for index in VideoMetric.__table__.indexes
    }

    assert metric_indexes["ix_video_metrics_video_id_captured_at"] == [
        "video_id",
        "captured_at",
    ]


def test_video_metric_values_have_database_checks() -> None:
    metric_checks = {
        constraint.name
        for constraint in VideoMetric.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert {
        "ck_video_metrics_views_nonnegative",
        "ck_video_metrics_likes_nonnegative",
        "ck_video_metrics_comments_nonnegative",
        "ck_video_metrics_shares_nonnegative",
        "ck_video_metrics_watch_time_seconds_nonnegative",
        "ck_video_metrics_average_view_duration_seconds_nonnegative",
        "ck_video_metrics_impressions_nonnegative",
        "ck_video_metrics_click_through_rate_ratio",
    } <= metric_checks


def test_foreign_keys_are_restrictive() -> None:
    for column in (
        WorkspaceMembership.__table__.c.workspace_id,
        WorkspaceMembership.__table__.c.user_id,
        AuthSession.__table__.c.user_id,
        PasswordResetToken.__table__.c.user_id,
        Channel.__table__.c.user_id,
        Channel.__table__.c.workspace_id,
        Video.__table__.c.channel_id,
        VideoMetric.__table__.c.video_id,
    ):
        foreign_key = next(iter(column.foreign_keys))
        assert foreign_key.ondelete == "RESTRICT"


def test_relationships_do_not_delete_related_records() -> None:
    relationships = (
        User.channels,
        Channel.videos,
        Video.metrics,
    )

    for relationship in relationships:
        assert "delete" not in relationship.property.cascade
        assert "delete-orphan" not in relationship.property.cascade


def test_timestamps_are_timezone_aware() -> None:
    timestamp_columns = (
        User.__table__.c.created_at,
        User.__table__.c.updated_at,
        Channel.__table__.c.created_at,
        Channel.__table__.c.updated_at,
        Video.__table__.c.published_at,
        Video.__table__.c.created_at,
        Video.__table__.c.updated_at,
        VideoMetric.__table__.c.captured_at,
    )

    assert all(column.type.timezone for column in timestamp_columns)


def test_expected_unique_constraints_use_named_metadata() -> None:
    assert any(
        isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_channels_platform_platform_channel_id"
        for constraint in Channel.__table__.constraints
    )
    assert any(
        isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_videos_channel_id_platform_video_id"
        for constraint in Video.__table__.constraints
    )
