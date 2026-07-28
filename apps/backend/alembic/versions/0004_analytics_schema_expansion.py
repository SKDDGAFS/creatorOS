"""Expand cross-platform analytics with nullable and structured metrics.

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-29
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EXISTING_COUNT_FIELDS = (
    "views",
    "likes",
    "comments",
    "shares",
    "watch_time_seconds",
    "average_view_duration_seconds",
    "impressions",
)

NEW_COUNT_FIELDS = (
    "unique_viewers",
    "engaged_views",
    "completed_views",
    "saves",
    "views_from_impressions",
    "followers_gained",
    "followers_lost",
    "new_viewers",
    "returning_viewers",
    "first_hour_views",
    "first_hour_likes",
    "first_hour_comments",
    "first_hour_shares",
    "first_hour_saves",
    "first_hour_watch_time_seconds",
    "first_hour_followers_gained",
    "first_hour_impressions",
)


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def _ratio_check(table: str, column: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(
        f"{column} >= 0 AND {column} <= 1",
        name=op.f(f"ck_{table}_{column}"),
    )


def _nullable_count_check(table: str, column: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(
        f"{column} IS NULL OR {column} >= 0",
        name=op.f(f"ck_{table}_{column}_nonnegative"),
    )


def upgrade() -> None:
    op.add_column(
        "videos",
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_videos_duration_seconds_positive"),
        "videos",
        "duration_seconds IS NULL OR duration_seconds > 0",
    )

    for field_name in EXISTING_COUNT_FIELDS:
        op.alter_column(
            "video_metrics",
            field_name,
            existing_type=sa.BigInteger(),
            server_default=None,
            nullable=True,
        )
    op.alter_column(
        "video_metrics",
        "click_through_rate",
        existing_type=sa.Numeric(7, 4),
        type_=sa.Numeric(9, 6),
        server_default=None,
        nullable=True,
    )

    for field_name in NEW_COUNT_FIELDS:
        op.add_column(
            "video_metrics",
            sa.Column(field_name, sa.BigInteger(), nullable=True),
        )
        op.create_check_constraint(
            op.f(f"ck_video_metrics_{field_name}_nonnegative"),
            "video_metrics",
            f"{field_name} IS NULL OR {field_name} >= 0",
        )

    op.create_table(
        "video_retention_points",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("video_metric_id", _uuid(), nullable=False),
        sa.Column("position_ratio", sa.Numeric(7, 6), nullable=False),
        sa.Column("audience_retention_ratio", sa.Numeric(7, 6), nullable=False),
        sa.ForeignKeyConstraint(
            ["video_metric_id"],
            ["video_metrics.id"],
            name="fk_video_retention_points_video_metric_id_video_metrics",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_video_retention_points"),
        _ratio_check("video_retention_points", "position_ratio"),
        _ratio_check("video_retention_points", "audience_retention_ratio"),
        sa.UniqueConstraint(
            "video_metric_id",
            "position_ratio",
            name="uq_video_retention_points_metric_position",
        ),
    )
    op.create_index(
        "ix_video_retention_points_video_metric_id",
        "video_retention_points",
        ["video_metric_id"],
    )

    op.create_table(
        "video_traffic_sources",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("video_metric_id", _uuid(), nullable=False),
        sa.Column("source_type", sa.String(100), nullable=False),
        sa.Column("views", sa.BigInteger(), nullable=True),
        sa.Column("watch_time_seconds", sa.BigInteger(), nullable=True),
        sa.Column("percentage", sa.Numeric(7, 6), nullable=True),
        sa.ForeignKeyConstraint(
            ["video_metric_id"],
            ["video_metrics.id"],
            name="fk_video_traffic_sources_video_metric_id_video_metrics",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_video_traffic_sources"),
        _nullable_count_check("video_traffic_sources", "views"),
        _nullable_count_check("video_traffic_sources", "watch_time_seconds"),
        sa.CheckConstraint(
            "percentage IS NULL OR (percentage >= 0 AND percentage <= 1)",
            name=op.f("ck_video_traffic_sources_percentage_ratio"),
        ),
        sa.UniqueConstraint(
            "video_metric_id",
            "source_type",
            name="uq_video_traffic_sources_metric_source",
        ),
    )
    op.create_index(
        "ix_video_traffic_sources_video_metric_id",
        "video_traffic_sources",
        ["video_metric_id"],
    )

    op.create_table(
        "video_audience_demographics",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("video_metric_id", _uuid(), nullable=False),
        sa.Column("dimension", sa.String(50), nullable=False),
        sa.Column("segment", sa.String(100), nullable=False),
        sa.Column("viewers", sa.BigInteger(), nullable=True),
        sa.Column("percentage", sa.Numeric(7, 6), nullable=True),
        sa.ForeignKeyConstraint(
            ["video_metric_id"],
            ["video_metrics.id"],
            name="fk_video_audience_demographics_video_metric_id_video_metrics",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_video_audience_demographics"),
        _nullable_count_check("video_audience_demographics", "viewers"),
        sa.CheckConstraint(
            "percentage IS NULL OR (percentage >= 0 AND percentage <= 1)",
            name=op.f("ck_video_audience_demographics_percentage_ratio"),
        ),
        sa.UniqueConstraint(
            "video_metric_id",
            "dimension",
            "segment",
            name="uq_video_audience_demographics_metric_segment",
        ),
    )
    op.create_index(
        "ix_video_audience_demographics_video_metric_id",
        "video_audience_demographics",
        ["video_metric_id"],
    )

    op.create_table(
        "video_audience_geography",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("video_metric_id", _uuid(), nullable=False),
        sa.Column("country_code", sa.String(2), nullable=False),
        sa.Column("viewers", sa.BigInteger(), nullable=True),
        sa.Column("percentage", sa.Numeric(7, 6), nullable=True),
        sa.ForeignKeyConstraint(
            ["video_metric_id"],
            ["video_metrics.id"],
            name="fk_video_audience_geography_video_metric_id_video_metrics",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_video_audience_geography"),
        _nullable_count_check("video_audience_geography", "viewers"),
        sa.CheckConstraint(
            "percentage IS NULL OR (percentage >= 0 AND percentage <= 1)",
            name=op.f("ck_video_audience_geography_percentage_ratio"),
        ),
        sa.UniqueConstraint(
            "video_metric_id",
            "country_code",
            name="uq_video_audience_geography_metric_country",
        ),
    )
    op.create_index(
        "ix_video_audience_geography_video_metric_id",
        "video_audience_geography",
        ["video_metric_id"],
    )

    op.create_table(
        "video_discovery_assets",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("video_metric_id", _uuid(), nullable=False),
        sa.Column("asset_type", sa.String(30), nullable=False),
        sa.Column("asset_value", sa.String(500), nullable=False),
        sa.Column("views", sa.BigInteger(), nullable=True),
        sa.Column("percentage", sa.Numeric(7, 6), nullable=True),
        sa.ForeignKeyConstraint(
            ["video_metric_id"],
            ["video_metrics.id"],
            name="fk_video_discovery_assets_video_metric_id_video_metrics",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_video_discovery_assets"),
        sa.CheckConstraint(
            "asset_type IN "
            "('hashtag', 'sound', 'search_term', 'external_referrer', 'other')",
            name=op.f("ck_video_discovery_assets_asset_type_allowed"),
        ),
        _nullable_count_check("video_discovery_assets", "views"),
        sa.CheckConstraint(
            "percentage IS NULL OR (percentage >= 0 AND percentage <= 1)",
            name=op.f("ck_video_discovery_assets_percentage_ratio"),
        ),
        sa.UniqueConstraint(
            "video_metric_id",
            "asset_type",
            "asset_value",
            name="uq_video_discovery_assets_metric_asset",
        ),
    )
    op.create_index(
        "ix_video_discovery_assets_video_metric_id",
        "video_discovery_assets",
        ["video_metric_id"],
    )

    op.create_table(
        "tiktok_metric_extensions",
        sa.Column("video_metric_id", _uuid(), nullable=False),
        sa.Column("for_you_views", sa.BigInteger(), nullable=True),
        sa.Column("following_feed_views", sa.BigInteger(), nullable=True),
        sa.Column("search_views", sa.BigInteger(), nullable=True),
        sa.Column("profile_views", sa.BigInteger(), nullable=True),
        sa.Column("sound_views", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(
            ["video_metric_id"],
            ["video_metrics.id"],
            name="fk_tiktok_metric_extensions_video_metric_id_video_metrics",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "video_metric_id",
            name="pk_tiktok_metric_extensions",
        ),
        *(
            _nullable_count_check("tiktok_metric_extensions", field_name)
            for field_name in (
                "for_you_views",
                "following_feed_views",
                "search_views",
                "profile_views",
                "sound_views",
            )
        ),
    )

    op.create_table(
        "instagram_metric_extensions",
        sa.Column("video_metric_id", _uuid(), nullable=False),
        sa.Column("reels_tab_reach", sa.BigInteger(), nullable=True),
        sa.Column("feed_reach", sa.BigInteger(), nullable=True),
        sa.Column("explore_reach", sa.BigInteger(), nullable=True),
        sa.Column("profile_reach", sa.BigInteger(), nullable=True),
        sa.Column("accounts_reached", sa.BigInteger(), nullable=True),
        sa.Column("accounts_engaged", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(
            ["video_metric_id"],
            ["video_metrics.id"],
            name="fk_instagram_metric_extensions_video_metric_id_video_metrics",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "video_metric_id",
            name="pk_instagram_metric_extensions",
        ),
        *(
            _nullable_count_check("instagram_metric_extensions", field_name)
            for field_name in (
                "reels_tab_reach",
                "feed_reach",
                "explore_reach",
                "profile_reach",
                "accounts_reached",
                "accounts_engaged",
            )
        ),
    )

    op.create_table(
        "youtube_metric_extensions",
        sa.Column("video_metric_id", _uuid(), nullable=False),
        sa.Column("suggested_video_views", sa.BigInteger(), nullable=True),
        sa.Column("browse_feature_views", sa.BigInteger(), nullable=True),
        sa.Column("subscriber_views", sa.BigInteger(), nullable=True),
        sa.Column("unsubscribed_views", sa.BigInteger(), nullable=True),
        sa.Column("search_views", sa.BigInteger(), nullable=True),
        sa.Column("external_views", sa.BigInteger(), nullable=True),
        sa.Column("end_screen_views", sa.BigInteger(), nullable=True),
        sa.Column("reported_impressions_ctr", sa.Numeric(9, 6), nullable=True),
        sa.ForeignKeyConstraint(
            ["video_metric_id"],
            ["video_metrics.id"],
            name="fk_youtube_metric_extensions_video_metric_id_video_metrics",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "video_metric_id",
            name="pk_youtube_metric_extensions",
        ),
        *(
            _nullable_count_check("youtube_metric_extensions", field_name)
            for field_name in (
                "suggested_video_views",
                "browse_feature_views",
                "subscriber_views",
                "unsubscribed_views",
                "search_views",
                "external_views",
                "end_screen_views",
            )
        ),
        sa.CheckConstraint(
            "reported_impressions_ctr IS NULL OR "
            "(reported_impressions_ctr >= 0 AND reported_impressions_ctr <= 1)",
            name=op.f(
                "ck_youtube_metric_extensions_reported_impressions_ctr_ratio"
            ),
        ),
    )


def downgrade() -> None:
    op.drop_table("youtube_metric_extensions")
    op.drop_table("instagram_metric_extensions")
    op.drop_table("tiktok_metric_extensions")
    op.drop_index(
        "ix_video_discovery_assets_video_metric_id",
        table_name="video_discovery_assets",
    )
    op.drop_table("video_discovery_assets")
    op.drop_index(
        "ix_video_audience_geography_video_metric_id",
        table_name="video_audience_geography",
    )
    op.drop_table("video_audience_geography")
    op.drop_index(
        "ix_video_audience_demographics_video_metric_id",
        table_name="video_audience_demographics",
    )
    op.drop_table("video_audience_demographics")
    op.drop_index(
        "ix_video_traffic_sources_video_metric_id",
        table_name="video_traffic_sources",
    )
    op.drop_table("video_traffic_sources")
    op.drop_index(
        "ix_video_retention_points_video_metric_id",
        table_name="video_retention_points",
    )
    op.drop_table("video_retention_points")

    for field_name in reversed(NEW_COUNT_FIELDS):
        op.drop_constraint(
            f"ck_video_metrics_{field_name}_nonnegative",
            "video_metrics",
            type_="check",
        )
        op.drop_column("video_metrics", field_name)

    nullable_fields = (*EXISTING_COUNT_FIELDS, "click_through_rate")
    assignments = ", ".join(
        f"{field_name} = COALESCE({field_name}, 0)"
        for field_name in nullable_fields
    )
    op.execute(f"UPDATE video_metrics SET {assignments}")

    for field_name in EXISTING_COUNT_FIELDS:
        op.alter_column(
            "video_metrics",
            field_name,
            existing_type=sa.BigInteger(),
            server_default=sa.text("'0'"),
            nullable=False,
        )
    op.alter_column(
        "video_metrics",
        "click_through_rate",
        existing_type=sa.Numeric(9, 6),
        type_=sa.Numeric(7, 4),
        server_default=sa.text("'0'"),
        nullable=False,
    )

    op.drop_constraint(
        "ck_videos_duration_seconds_positive",
        "videos",
        type_="check",
    )
    op.drop_column("videos", "duration_seconds")
