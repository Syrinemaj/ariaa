"""Add connection_id to automation_runs

Revision ID: 022
Revises: 021
Create Date: 2026-10-06

Feature: Connections (Phase 4 Step 9) — "every execution records which
connection was used". Nullable because historical rows predate connections
and the raw base_url/auth_headers path they used no longer exists to
backfill from.
"""
from alembic import op
import sqlalchemy as sa

revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "automation_runs",
        sa.Column("connection_id", sa.String(), sa.ForeignKey("connections.id"), nullable=True),
    )
    op.create_index("ix_automation_runs_connection_id", "automation_runs", ["connection_id"])


def downgrade() -> None:
    op.drop_index("ix_automation_runs_connection_id", table_name="automation_runs")
    op.drop_column("automation_runs", "connection_id")
