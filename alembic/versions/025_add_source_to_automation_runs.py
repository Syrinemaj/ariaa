"""Add source ('simple'|'bulk') to automation_runs

Revision ID: 025
Revises: 024
Create Date: 2026-10-12

Both Simple Automation (app/automation/service.py) and Bulk Execution
(app/bulk_execution/service.py) write to the SAME automation_runs table —
there was no column distinguishing them, so /automation-list (the
"Automations" page) could only show an unlabeled mix of both, and couldn't
filter by type. Historical rows are backfilled from a reliable existing
signal: a bulk_batches row referencing the run only ever gets created by
Bulk Execution (see app/bulk_execution/batch_executor.py), so any
automation_run with at least one is unambiguously 'bulk'; everything else
defaults to 'simple'.
"""
from alembic import op
import sqlalchemy as sa

revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "automation_runs",
        sa.Column("source", sa.String(), nullable=False, server_default="simple"),
    )
    op.execute(
        """
        UPDATE automation_runs
        SET source = 'bulk'
        WHERE id IN (SELECT DISTINCT automation_run_id FROM bulk_batches)
        """
    )


def downgrade() -> None:
    op.drop_column("automation_runs", "source")
