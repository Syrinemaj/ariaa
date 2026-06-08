"""Switch endpoint_embeddings.embedding from vector(1536) to vector(384)

Revision ID: 011
Revises: 010
Create Date: 2026-05-30

Background
----------
ARIA now uses all-MiniLM-L6-v2 (sentence-transformers) for local embeddings
instead of Azure text-embedding-3-small. The new model outputs 384 dimensions
instead of 1536.

pgvector vectors are dimension-typed: a vector(1536) column cannot store
a 384-float vector. The types are completely incompatible — there is no
lossless conversion.

What this migration does
------------------------
1. Drops the HNSW index (it is dimension-specific and must be rebuilt).
2. TRUNCATES endpoint_embeddings — all existing 1536-dim vectors are
   permanently discarded. They cannot be down-projected to 384 dims without
   retraining, and they would be meaningless for semantic search anyway.
3. Drops the old 1536-dim column and adds a new 384-dim column.
4. Recreates the HNSW index for cosine distance at 384 dims.

⚠️  DATA LOSS WARNING
After running this migration you MUST re-embed every endpoint.
Use the Celery task or the management command:

    # Re-embed all runs (all orgs) via Celery:
    for run_id in $(psql -c "SELECT id FROM analysis_runs WHERE status='completed'" -t):
        celery call aria.tasks.embedding.index_run_embeddings \
            --kwargs='{"run_id":"'$run_id'","org_id":"..."}'

    # Or trigger via the API:
    POST /rag/index/{run_id}

Downgrade note
--------------
Downgrade restores the vector(1536) column schema but does NOT restore the
data (it was truncated in upgrade). You must re-embed with Azure after downgrade.
"""
import sqlalchemy as sa
from alembic import op

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None

_TABLE = "endpoint_embeddings"
_COL = "embedding"
_HNSW_IDX = "idx_endpoint_embeddings_hnsw"


def upgrade() -> None:
    # 1. Drop HNSW index (dimension-specific, cannot be reused)
    op.execute(f"DROP INDEX IF EXISTS {_HNSW_IDX}")

    # 2. Truncate — existing 1536-dim vectors are incompatible with 384 dims.
    #    CASCADE not needed: no FK references endpoint_embeddings from other tables.
    op.execute(f"TRUNCATE TABLE {_TABLE}")

    # 3. Replace the column with the new dimension.
    #    DROP + ADD is cleaner than ALTER TYPE which requires a USING expression
    #    and can fail on non-empty tables.
    op.execute(f"ALTER TABLE {_TABLE} DROP COLUMN {_COL}")
    op.execute(
        f"ALTER TABLE {_TABLE} "
        f"ADD COLUMN {_COL} vector(384) NOT NULL "
        f"DEFAULT array_fill(0, ARRAY[384])::vector"
    )
    # Remove default — vectors must always be computed, never left as zeros
    op.execute(
        f"ALTER TABLE {_TABLE} ALTER COLUMN {_COL} DROP DEFAULT"
    )

    # 4. Recreate HNSW index for 384-dim cosine distance.
    #    Table is empty so the brief lock is negligible.
    op.execute(f"""
        CREATE INDEX {_HNSW_IDX}
        ON {_TABLE}
        USING hnsw ({_COL} vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    """)


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {_HNSW_IDX}")
    op.execute(f"TRUNCATE TABLE {_TABLE}")
    op.execute(f"ALTER TABLE {_TABLE} DROP COLUMN {_COL}")
    op.execute(
        f"ALTER TABLE {_TABLE} "
        f"ADD COLUMN {_COL} vector(1536) NOT NULL "
        f"DEFAULT array_fill(0, ARRAY[1536])::vector"
    )
    op.execute(
        f"ALTER TABLE {_TABLE} ALTER COLUMN {_COL} DROP DEFAULT"
    )
    op.execute(f"""
        CREATE INDEX {_HNSW_IDX}
        ON {_TABLE}
        USING hnsw ({_COL} vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    """)
