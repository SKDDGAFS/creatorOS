"""Add contextual growth-signal profiles and weights.

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-29
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SIGNAL_VALUES = (
    "'retention_curve', 'completion_rate', 'average_percentage_viewed', "
    "'first_hour_performance', 'share_rate', 'follower_conversion_rate', "
    "'recommendation_traffic', 'new_viewer_reach', "
    "'impressions_to_view_rate', 'returning_viewer_trend', 'save_rate', "
    "'normalized_engagement_rate', 'search_traffic', 'hashtag_reach', "
    "'sound_reach', 'posting_time_performance', 'geographic_fit', "
    "'raw_likes', 'raw_comments', 'raw_views', 'raw_impressions', "
    "'demographic_breakdown'"
)


def upgrade() -> None:
    op.create_table(
        "growth_signal_profiles",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(20), nullable=True),
        sa.Column("content_format", sa.String(50), nullable=True),
        sa.Column("account_size_min", sa.Integer(), nullable=True),
        sa.Column("account_size_max", sa.Integer(), nullable=True),
        sa.Column(
            "video_duration_min_seconds",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "video_duration_max_seconds",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column("goal", sa.String(100), nullable=True),
        sa.Column(
            "evidence_min",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("evidence_max", sa.Integer(), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_growth_signal_profiles_workspace_id_workspaces",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_growth_signal_profiles_created_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_growth_signal_profiles"),
        sa.UniqueConstraint(
            "workspace_id",
            "name",
            "version",
            name="uq_growth_signal_profiles_workspace_name_version",
        ),
        sa.CheckConstraint(
            "platform IS NULL OR "
            "platform IN ('youtube', 'tiktok', 'instagram')",
            name=op.f("ck_growth_signal_profiles_platform_allowed"),
        ),
        sa.CheckConstraint(
            "account_size_min IS NULL OR account_size_min >= 0",
            name=op.f(
                "ck_growth_signal_profiles_account_size_min_nonnegative"
            ),
        ),
        sa.CheckConstraint(
            "account_size_max IS NULL OR account_size_max >= 0",
            name=op.f(
                "ck_growth_signal_profiles_account_size_max_nonnegative"
            ),
        ),
        sa.CheckConstraint(
            "account_size_min IS NULL OR account_size_max IS NULL "
            "OR account_size_min <= account_size_max",
            name=op.f("ck_growth_signal_profiles_account_size_range"),
        ),
        sa.CheckConstraint(
            "video_duration_min_seconds IS NULL "
            "OR video_duration_min_seconds > 0",
            name=op.f(
                "ck_growth_signal_profiles_video_duration_min_positive"
            ),
        ),
        sa.CheckConstraint(
            "video_duration_max_seconds IS NULL "
            "OR video_duration_max_seconds > 0",
            name=op.f(
                "ck_growth_signal_profiles_video_duration_max_positive"
            ),
        ),
        sa.CheckConstraint(
            "video_duration_min_seconds IS NULL "
            "OR video_duration_max_seconds IS NULL "
            "OR video_duration_min_seconds <= video_duration_max_seconds",
            name=op.f("ck_growth_signal_profiles_video_duration_range"),
        ),
        sa.CheckConstraint(
            "evidence_min >= 0",
            name=op.f(
                "ck_growth_signal_profiles_evidence_min_nonnegative"
            ),
        ),
        sa.CheckConstraint(
            "evidence_max IS NULL OR evidence_max >= evidence_min",
            name=op.f("ck_growth_signal_profiles_evidence_range"),
        ),
        sa.CheckConstraint(
            "version >= 1",
            name=op.f("ck_growth_signal_profiles_version_positive"),
        ),
    )
    op.create_index(
        "ix_growth_signal_profiles_workspace_id",
        "growth_signal_profiles",
        ["workspace_id"],
    )
    op.create_index(
        "ix_growth_signal_profiles_created_by_user_id",
        "growth_signal_profiles",
        ["created_by_user_id"],
    )

    op.create_table(
        "growth_signal_weights",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "profile_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("signal", sa.String(60), nullable=False),
        sa.Column("tier", sa.String(20), nullable=False),
        sa.Column("weight", sa.Numeric(9, 6), nullable=False),
        sa.Column("minimum_sample_size", sa.Integer(), nullable=False),
        sa.Column(
            "full_confidence_sample_size",
            sa.Integer(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["growth_signal_profiles.id"],
            name="fk_growth_signal_weights_profile_id_growth_signal_profiles",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_growth_signal_weights"),
        sa.UniqueConstraint(
            "profile_id",
            "signal",
            name="uq_growth_signal_weights_profile_signal",
        ),
        sa.CheckConstraint(
            f"signal IN ({SIGNAL_VALUES})",
            name=op.f("ck_growth_signal_weights_signal_allowed"),
        ),
        sa.CheckConstraint(
            "tier IN ('strong', 'medium', 'contextual')",
            name=op.f("ck_growth_signal_weights_tier_allowed"),
        ),
        sa.CheckConstraint(
            "weight > 0 AND weight <= 100",
            name=op.f("ck_growth_signal_weights_weight_range"),
        ),
        sa.CheckConstraint(
            "minimum_sample_size >= 1",
            name=op.f(
                "ck_growth_signal_weights_minimum_sample_size_positive"
            ),
        ),
        sa.CheckConstraint(
            "full_confidence_sample_size >= minimum_sample_size",
            name=op.f(
                "ck_growth_signal_weights_confidence_sample_range"
            ),
        ),
    )
    op.create_index(
        "ix_growth_signal_weights_profile_id",
        "growth_signal_weights",
        ["profile_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_growth_signal_weights_profile_id",
        table_name="growth_signal_weights",
    )
    op.drop_table("growth_signal_weights")
    op.drop_index(
        "ix_growth_signal_profiles_created_by_user_id",
        table_name="growth_signal_profiles",
    )
    op.drop_index(
        "ix_growth_signal_profiles_workspace_id",
        table_name="growth_signal_profiles",
    )
    op.drop_table("growth_signal_profiles")
