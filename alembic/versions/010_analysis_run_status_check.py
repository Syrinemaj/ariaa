"""CHECK constraint on analysis_runs.status + default change

Revision ID: 010
Revises: 009
Create Date: 2026-05-30

Changes:
1. Add CHECK constraint on analysis_runs.status restricting values to
   ('processing', 'completed', 'failed').
2. Backfill any rows that still hold the old default 'completed' — the
   application code now creates rows with status='processing' and updates
   them on completion, but rows created before this migration may still
   have arbitrary string values.
3. The server_default is updated to 'processing' to match the ORM default.
"""
import sqlalchemy as sa
from alembic import op

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None

_VALID_STATUSES = ("processing", "completed", "failed")
_CONSTRAINT_NAME = "ck_analysis_runs_status"


def upgrade() -> None:
    bind = op.get_bind()

    # Normalise any stale or unknown status values before adding the constraint.
    # Rows with status NOT IN the valid set are set to 'completed' because they
    # were written by the old code that only ever produced 'completed'.
    valid_list = ", ".join(f"'{s}'" for s in _VALID_STATUSES)
    op.execute(f"""
        UPDATE analysis_runs
        SET status = 'completed'
        WHERE status NOT IN ({valid_list})
    """)

    op.execute(f"""
        ALTER TABLE analysis_runs
        ADD CONSTRAINT {_CONSTRAINT_NAME}
        CHECK (status IN ({valid_list}))
    """)

    # Update the column server_default so new rows created outside the ORM
    # (e.g. admin scripts, migrations) also get 'processing'.
    op.alter_column(
        "analysis_runs",
        "status",
        server_default="processing",
        existing_type=sa.String(),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.execute(f"ALTER TABLE analysis_runs DROP CONSTRAINT IF EXISTS {_CONSTRAINT_NAME}")
    op.alter_column(
        "analysis_runs",
        "status",
        server_default="completed",
        existing_type=sa.String(),
        existing_nullable=False,
    )
