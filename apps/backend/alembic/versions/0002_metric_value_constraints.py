"""Add metric value constraints.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-28
"""

from collections.abc import Sequence

from alembic import op


revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


METRIC_CHECKS = (
    ("ck_video_metrics_views_nonnegative", "views >= 0"),
    ("ck_video_metrics_likes_nonnegative", "likes >= 0"),
    ("ck_video_metrics_comments_nonnegative", "comments >= 0"),
    ("ck_video_metrics_shares_nonnegative", "shares >= 0"),
    (
        "ck_video_metrics_watch_time_seconds_nonnegative",
        "watch_time_seconds >= 0",
    ),
    (
        "ck_video_metrics_average_view_duration_seconds_nonnegative",
        "average_view_duration_seconds >= 0",
    ),
    ("ck_video_metrics_impressions_nonnegative", "impressions >= 0"),
    (
        "ck_video_metrics_click_through_rate_ratio",
        "click_through_rate >= 0 AND click_through_rate <= 1",
    ),
)


def upgrade() -> None:
    for constraint_name, condition in METRIC_CHECKS:
        op.create_check_constraint(
            op.f(constraint_name),
            "video_metrics",
            condition,
        )


def downgrade() -> None:
    for constraint_name, _ in reversed(METRIC_CHECKS):
        op.drop_constraint(
            op.f(constraint_name),
            "video_metrics",
            type_="check",
        )
