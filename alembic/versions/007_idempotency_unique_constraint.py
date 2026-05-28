"""Idempotency unique constraint + org_id column

Revision ID: 007
Revises: 006
Create Date: 2026-05-28

Changes:
1. Add org_id column to idempotency_records (nullable initially, then NOT NULL)
2. Add UNIQUE (idempotency_key, endpoint_key) constraint
   Required for INSERT ON CONFLICT DO NOTHING RETURNING id to work correctly.
3. Add automation_run_id index for reporting queries
"""
import sqlalchemy as sa
from alembic import op

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def _col_exists(bind, table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Add org_id column if missing
    if not _col_exists(bind, "idempotency_records", "org_id"):
        op.add_column(
            "idempotency_records",
            sa.Column("org_id", sa.String(), nullable=True),
        )
        # Backfill with empty string (no org info in old rows)
        op.execute("UPDATE idempotency_records SET org_id = '' WHERE org_id IS NULL")
        op.alter_column("idempotency_records", "org_id", nullable=False)

    # 2. UNIQUE constraint — required for atomic INSERT ON CONFLICT DO NOTHING
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'uq_idempotency_key_endpoint'
            ) THEN
                ALTER TABLE idempotency_records
                ADD CONSTRAINT uq_idempotency_key_endpoint
                UNIQUE (idempotency_key, endpoint_key);
            END IF;
        END$$;
    """)

    # 3. Index on automation_run_id for reporting
    op.execute("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_idempotency_automation_run
        ON idempotency_records(automation_run_id)
    """)

    # 4. Add updated_at if missing (TimestampMixin compatibility)
    if not _col_exists(bind, "idempotency_records", "updated_at"):
        op.add_column(
            "idempotency_records",
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
        )


def downgrade() -> None:
    op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_idempotency_automation_run")
    op.execute("""
        ALTER TABLE idempotency_records
        DROP CONSTRAINT IF EXISTS uq_idempotency_key_endpoint
    """)
    bind = op.get_bind()
    if _col_exists(bind, "idempotency_records", "org_id"):
        op.drop_column("idempotency_records", "org_id")
