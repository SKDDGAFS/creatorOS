"""Add strategy recommendations, evidence, results, and evaluations.

Revision ID: 0015
Revises: 0014
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "recommendations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "growth_signal_profile_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("proposed_action", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("expected_effect", sa.Text(), nullable=False),
        sa.Column("uncertainty", sa.Text(), nullable=False),
        sa.Column("linked_goal", sa.String(255), nullable=False),
        sa.Column("expected_impact", sa.String(20), nullable=False),
        sa.Column("effort_estimate", sa.String(20), nullable=False),
        sa.Column("risk_level", sa.String(20), nullable=False),
        sa.Column("confidence", sa.Numeric(9, 6), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), server_default="proposed", nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('proposed', 'accepted', 'in_progress', "
            "'completed', 'dismissed')",
            name=op.f("ck_recommendations_status_allowed"),
        ),
        sa.CheckConstraint(
            "expected_impact IN ('low', 'medium', 'high')",
            name=op.f("ck_recommendations_expected_impact_allowed"),
        ),
        sa.CheckConstraint(
            "effort_estimate IN ('low', 'medium', 'high')",
            name=op.f("ck_recommendations_effort_estimate_allowed"),
        ),
        sa.CheckConstraint(
            "risk_level IN ('low', 'medium', 'high')",
            name=op.f("ck_recommendations_risk_level_allowed"),
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name=op.f("ck_recommendations_confidence_range"),
        ),
        sa.CheckConstraint(
            "sample_size >= 1",
            name=op.f("ck_recommendations_sample_size_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["growth_signal_profile_id"],
            ["growth_signal_profiles.id"],
            name="fk_recommendations_signal_profile",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "fingerprint",
            name="uq_recommendations_workspace_fingerprint",
        ),
    )
    for column in (
        "workspace_id",
        "created_by_user_id",
        "growth_signal_profile_id",
        "linked_goal",
        "status",
    ):
        op.create_index(f"ix_recommendations_{column}", "recommendations", [column])

    op.create_table(
        "recommendation_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recommendation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("research_finding_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("signal", sa.String(60), nullable=False),
        sa.Column("metric_name", sa.String(255), nullable=False),
        sa.Column("normalized_value", sa.Numeric(9, 6), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("source_confidence", sa.Numeric(9, 6), nullable=False),
        sa.Column("explanation", sa.String(2000), nullable=False),
        sa.CheckConstraint(
            "signal IN ('retention_curve', 'completion_rate', "
            "'average_percentage_viewed', 'first_hour_performance', "
            "'share_rate', 'follower_conversion_rate', "
            "'recommendation_traffic', 'new_viewer_reach', "
            "'impressions_to_view_rate', 'returning_viewer_trend', "
            "'save_rate', 'normalized_engagement_rate', 'search_traffic', "
            "'hashtag_reach', 'sound_reach', 'posting_time_performance', "
            "'geographic_fit', 'raw_likes', 'raw_comments', 'raw_views', "
            "'raw_impressions', 'demographic_breakdown')",
            name=op.f("ck_recommendation_evidence_signal_allowed"),
        ),
        sa.CheckConstraint(
            "normalized_value >= 0 AND normalized_value <= 1",
            name=op.f("ck_recommendation_evidence_value_range"),
        ),
        sa.CheckConstraint(
            "source_confidence >= 0 AND source_confidence <= 1",
            name=op.f("ck_recommendation_evidence_source_confidence_range"),
        ),
        sa.CheckConstraint(
            "sample_size >= 1",
            name=op.f("ck_recommendation_evidence_sample_size_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["recommendation_id"], ["recommendations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["research_finding_id"],
            ["research_findings.id"],
            name="fk_recommendation_evidence_research_finding",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "recommendation_id",
            "signal",
            name="uq_recommendation_evidence_recommendation_signal",
        ),
    )
    for column in ("recommendation_id", "research_finding_id"):
        op.create_index(
            f"ix_recommendation_evidence_{column}",
            "recommendation_evidence",
            [column],
        )

    op.create_table(
        "recommendation_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recommendation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recorded_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("metric_name", sa.String(255), nullable=False),
        sa.Column("baseline_value", sa.Numeric(18, 6), nullable=False),
        sa.Column("observed_value", sa.Numeric(18, 6), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("measurement_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("measurement_ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.String(2000), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "sample_size >= 1",
            name=op.f("ck_recommendation_results_sample_size_positive"),
        ),
        sa.CheckConstraint(
            "measurement_ended_at > measurement_started_at",
            name=op.f("ck_recommendation_results_measurement_window_order"),
        ),
        sa.ForeignKeyConstraint(
            ["recommendation_id"],
            ["recommendations.id"],
            name="fk_recommendation_evaluations_recommendation",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "recommendation_id",
            "metric_name",
            "measurement_ended_at",
            name="uq_recommendation_results_metric_window",
        ),
    )
    for column in ("recommendation_id", "recorded_by_user_id"):
        op.create_index(
            f"ix_recommendation_results_{column}",
            "recommendation_results",
            [column],
        )

    op.create_table(
        "recommendation_outcome_evaluations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recommendation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conclusion", sa.String(30), nullable=False),
        sa.Column("average_relative_change", sa.Numeric(12, 6), nullable=True),
        sa.Column("confidence", sa.Numeric(9, 6), nullable=False),
        sa.Column("result_count", sa.Integer(), nullable=False),
        sa.Column("interpretation", sa.String(1000), nullable=False),
        sa.Column(
            "evaluated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "conclusion IN ('supported', 'inconclusive', 'not_supported')",
            name=op.f("ck_recommendation_outcome_evaluations_conclusion_allowed"),
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name=op.f("ck_recommendation_outcome_evaluations_confidence_range"),
        ),
        sa.CheckConstraint(
            "result_count >= 1",
            name=op.f("ck_recommendation_outcome_evaluations_result_count_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["recommendation_id"], ["recommendations.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("recommendation_id"),
    )
    op.create_index(
        "ix_recommendation_outcome_evaluations_recommendation_id",
        "recommendation_outcome_evaluations",
        ["recommendation_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_recommendation_outcome_evaluations_recommendation_id",
        table_name="recommendation_outcome_evaluations",
    )
    op.drop_table("recommendation_outcome_evaluations")
    for table_name, columns in (
        ("recommendation_results", ("recorded_by_user_id", "recommendation_id")),
        (
            "recommendation_evidence",
            ("research_finding_id", "recommendation_id"),
        ),
    ):
        for column in columns:
            op.drop_index(f"ix_{table_name}_{column}", table_name=table_name)
        op.drop_table(table_name)
    for column in (
        "status",
        "linked_goal",
        "growth_signal_profile_id",
        "created_by_user_id",
        "workspace_id",
    ):
        op.drop_index(f"ix_recommendations_{column}", table_name="recommendations")
    op.drop_table("recommendations")
