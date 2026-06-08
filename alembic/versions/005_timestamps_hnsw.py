"""Timestamps timezone-aware + HNSW index on embeddings

Revision ID: 005
Revises: 004
Create Date: 2026-05-28

Changes:
1. Convert all naive TIMESTAMP columns → TIMESTAMPTZ
2. Add updated_at column where missing (TimestampMixin)
3. Create HNSW index on endpoint_embeddings.embedding (CONCURRENTLY)
4. Trigger PostgreSQL pour updated_at auto-update sur UPDATE directs
"""
import sqlalchemy as sa
from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None

# Tables that had naive DateTime and need TIMESTAMPTZ
_TIMESTAMP_COLS: list[tuple[str, list[str]]] = [
    ("endpoint_embeddings", ["created_at"]),
    ("analysis_runs",       ["created_at"]),
    ("automation_runs",     ["created_at"]),
    ("automation_step_logs",["created_at"]),
    ("idempotency_records", ["created_at"]),
    ("bulk_batches",        ["created_at"]),
    ("workflows",           ["created_at"]),
    ("workflow_steps",      ["created_at"]),
]

# Tables that need an updated_at column added
_ADD_UPDATED_AT: list[str] = [
    "endpoint_embeddings",
    "analysis_runs",
    "automation_runs",
    "automation_step_logs",
    "idempotency_records",
    "bulk_batches",
]


def _col_exists(bind, table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()

    # ── 1. Convert TIMESTAMP → TIMESTAMPTZ ───────────────────────────────────
    for table, cols in _TIMESTAMP_COLS:
        for col in cols:
            if _col_exists(bind, table, col):
                op.execute(
                    f"ALTER TABLE {table} ALTER COLUMN {col} "
                    f"TYPE TIMESTAMPTZ USING {col} AT TIME ZONE 'UTC'"
                )

    # ── 2. Add updated_at where missing ───────────────────────────────────────
    for table in _ADD_UPDATED_AT:
        if not _col_exists(bind, table, "updated_at"):
            op.add_column(
                table,
                sa.Column(
                    "updated_at",
                    sa.DateTime(timezone=True),
                    nullable=False,
                    server_default=sa.text("now()"),
                ),
            )

    # ── 3. PostgreSQL trigger: auto-update updated_at on raw UPDATE ───────────
    # The ORM onupdate= handles it for ORM updates.
    # This trigger handles direct SQL UPDATE statements (migrations, admin tools).
    op.execute("""
        CREATE OR REPLACE FUNCTION _set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    for table in _ADD_UPDATED_AT:
        op.execute(f"""
            DROP TRIGGER IF EXISTS trg_{table}_updated_at ON {table};
            CREATE TRIGGER trg_{table}_updated_at
                BEFORE UPDATE ON {table}
                FOR EACH ROW EXECUTE FUNCTION _set_updated_at();
        """)

    # ── 4. HNSW index on endpoint_embeddings ─────────────────────────────────
    # Regular CREATE INDEX (no CONCURRENTLY): tables are empty at migration
    # time so the brief lock is negligible. CONCURRENTLY requires running
    # outside any transaction block, which Alembic cannot guarantee.
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_endpoint_embeddings_hnsw
        ON endpoint_embeddings
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_endpoint_embeddings_hnsw")

    bind = op.get_bind()
    for table in _ADD_UPDATED_AT:
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_updated_at ON {table}")
        if _col_exists(bind, table, "updated_at"):
            op.drop_column(table, "updated_at")

    for table, cols in _TIMESTAMP_COLS:
        for col in cols:
            if _col_exists(bind, table, col):
                op.execute(
                    f"ALTER TABLE {table} ALTER COLUMN {col} "
                    f"TYPE TIMESTAMP USING {col} AT TIME ZONE 'UTC'"
                )
