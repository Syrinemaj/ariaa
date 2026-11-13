"""Add job_id to analysis_runs

Revision ID: 019
Revises: 018
Create Date: 2026-10-02

Permet à GET /jobs/{job_id} de retomber sur la ligne AnalysisRun persistée
quand la clé Redis a expiré (TTL 24h) — voir C4 de l'audit. NULL pour
toutes les lignes existantes (pas de backfill, pas de donnée à reconstruire).
"""
from alembic import op
import sqlalchemy as sa

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("analysis_runs", sa.Column("job_id", sa.String(), nullable=True))
    op.create_index("ix_analysis_runs_job_id", "analysis_runs", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_analysis_runs_job_id", table_name="analysis_runs")
    op.drop_column("analysis_runs", "job_id")
