"""Add primary_entity, action, org_id to workflows for instruction-based lookup

Revision ID: 013
Revises: 012
Create Date: 2026-07-13

Changes:
  workflows.primary_entity  VARCHAR(100) NULL
    — main business entity this workflow operates on (e.g. "employee").
      No derivable source for existing rows — stays NULL until a future
      enrichment step populates it. Out of scope for this migration.
  workflows.action  VARCHAR(100) NULL
    — primary action type (create/update/delete/...). Same caveat as above.
  workflows.org_id  VARCHAR NULL, FK -> organizations.id, indexed
    — unlike the two columns above, this ONE is fully backfillable: every
      workflow already links to an analysis_run (run_id), which is already
      org-scoped. Backfilled below via a single UPDATE...FROM.

Why:
  Enables an automatic "find an existing workflow matching this intent"
  lookup in the planner (org_id + primary_entity + action), instead of a
  workflow only being reachable by manually picking a workflow_id.

# ARIA-WORKFLOW-V2: not added — confidence_score. WorkflowModel already has
# `confidence` (Float, default 0.0) serving the same purpose; a second,
# separately-maintained field would just drift out of sync with it. The
# planner lookup added later should ORDER BY the existing `confidence`
# column instead.
"""
from alembic import op
import sqlalchemy as sa


revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workflows",
        sa.Column("primary_entity", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "workflows",
        sa.Column("action", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "workflows",
        sa.Column(
            "org_id", sa.String(),
            sa.ForeignKey("organizations.id"),
            nullable=True,
        ),
    )
    op.create_index("ix_workflows_org_id", "workflows", ["org_id"])
    # Composite index for the planner lookup:
    # WHERE org_id = ? AND primary_entity = ? AND action = ? ORDER BY confidence DESC
    op.create_index(
        "ix_workflows_org_entity_action",
        "workflows",
        ["org_id", "primary_entity", "action"],
    )

    # Backfill org_id from the existing run_id -> analysis_runs.org_id link.
    # ARIA-WORKFLOW-V2: discovered live (Docker run, 2026-07-13) — at least
    # one analysis_runs row has org_id = '' (empty string, not NULL), which
    # is not a valid organizations.id and trips the FK constraint above.
    # Excluding NULL/'' so those workflows' org_id is simply left NULL
    # instead of failing the whole migration.
    op.execute(
        """
        UPDATE workflows
        SET org_id = analysis_runs.org_id
        FROM analysis_runs
        WHERE workflows.run_id = analysis_runs.id
          AND analysis_runs.org_id IS NOT NULL
          AND analysis_runs.org_id <> ''
        """
    )


def downgrade() -> None:
    op.drop_index("ix_workflows_org_entity_action", table_name="workflows")
    op.drop_index("ix_workflows_org_id", table_name="workflows")
    op.drop_column("workflows", "org_id")
    op.drop_column("workflows", "action")
    op.drop_column("workflows", "primary_entity")
