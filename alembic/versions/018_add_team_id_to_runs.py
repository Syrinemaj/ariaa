"""Add team_id to analysis_runs and automation_runs

Revision ID: 018
Revises: 017
Create Date: 2026-08-11

Phase 2 of the team feature: NULL team_id means "no team assigned /
org-wide visible" (all existing rows keep this default — no backfill).
Set at creation time when the creating user resolves to exactly one team
(see app.teams.service.resolve_single_team_id). Used by
app.security.tenancy.team_visibility_clause to scope OPERATOR visibility.
"""
from alembic import op
import sqlalchemy as sa

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analysis_runs",
        sa.Column("team_id", sa.String(), sa.ForeignKey("teams.id"), nullable=True),
    )
    op.create_index("ix_analysis_runs_team_id", "analysis_runs", ["team_id"])

    op.add_column(
        "automation_runs",
        sa.Column("team_id", sa.String(), sa.ForeignKey("teams.id"), nullable=True),
    )
    op.create_index("ix_automation_runs_team_id", "automation_runs", ["team_id"])


def downgrade() -> None:
    op.drop_index("ix_automation_runs_team_id", table_name="automation_runs")
    op.drop_column("automation_runs", "team_id")

    op.drop_index("ix_analysis_runs_team_id", table_name="analysis_runs")
    op.drop_column("analysis_runs", "team_id")
