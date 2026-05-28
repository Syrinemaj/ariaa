"""Org-scoped canonical key on endpoints table

Revision ID: 004
Revises: 003
Create Date: 2026-05-28

Changes:
- Adds UNIQUE constraint (org_id, canonical_key, run_id) on endpoints
- Backfills existing canonical_key rows to the new "{org_id}:{old_key}" format
- Converts endpoints.created_at to TIMESTAMPTZ
"""
import sqlalchemy as sa
from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Convert naive timestamp to TIMESTAMPTZ
    op.execute(
        "ALTER TABLE endpoints ALTER COLUMN created_at "
        "TYPE TIMESTAMPTZ USING created_at AT TIME ZONE 'UTC'"
    )

    # 2. Backfill canonical_key with org_id prefix for existing rows.
    #    New rows use build_registry_key() at the ORM layer, so only rows
    #    that pre-date this migration need the prefix.
    #    We detect pre-migration rows by the absence of a colon in canonical_key.
    op.execute("""
        UPDATE endpoints
        SET canonical_key = org_id || ':' || canonical_key
        WHERE canonical_key NOT LIKE '%:%'
    """)

    # 3. Add composite unique constraint
    op.create_unique_constraint(
        "uq_endpoints_org_canonical_run",
        "endpoints",
        ["org_id", "canonical_key", "run_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_endpoints_org_canonical_run", "endpoints", type_="unique")

    # Strip org_id prefix from canonical_key
    op.execute("""
        UPDATE endpoints
        SET canonical_key = substring(canonical_key FROM position(':' IN canonical_key) + 1)
        WHERE canonical_key LIKE '%:%'
    """)

    op.execute(
        "ALTER TABLE endpoints ALTER COLUMN created_at "
        "TYPE TIMESTAMP USING created_at AT TIME ZONE 'UTC'"
    )
