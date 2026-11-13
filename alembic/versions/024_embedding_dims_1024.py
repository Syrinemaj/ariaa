"""Switch endpoint_embeddings.embedding from vector(384) to vector(1024)

Revision ID: 024
Revises: 023
Create Date: 2026-10-10

Background
----------
The embedding provider default moved from LocalEmbeddingClient
(BAAI/bge-small-en, local sentence-transformers, English-only, 384 dims) to
BedrockEmbeddingClient (Cohere Embed Multilingual v3 via AWS Bedrock, 1024
dims) — see app/core/config.py::EMBEDDING_PROVIDER. bge-small-en could not
retrieve French content except by LLM-summarization accident; Cohere Embed
Multilingual v3 was chosen for real FR/EN cross-lingual retrieval. Amazon
Titan Text Embeddings V2, the documented one-line fallback
(BEDROCK_EMBEDDING_MODEL=amazon.titan-embed-text-v2:0), also defaults to
1024 dims, so this migration covers both without a second one.

pgvector vectors are dimension-typed: a vector(384) column cannot store a
1024-float vector. Same situation as migration 011 (1536 → 384).

What this migration does
-------------------------
1. Drops the HNSW index (dimension-specific, must be rebuilt).
2. TRUNCATES endpoint_embeddings — existing 384-dim vectors are permanently
   discarded, same reasoning as migration 011: not down/up-projectable
   without retraining, and meaningless for semantic search either way.
3. Drops the old 384-dim column and adds a new 1024-dim column.
4. Recreates the HNSW index for cosine distance at 1024 dims.

⚠️  DATA LOSS WARNING
After running this migration you MUST re-embed every endpoint (POST
/rag/index/{run_id} per completed analysis run, or the Celery task
aria.tasks.embedding.index_run_embeddings).

Downgrade note
---------------
Downgrade restores the vector(384) column schema but does NOT restore the
data (it was truncated in upgrade). You must re-embed with the local
provider after downgrade (set EMBEDDING_PROVIDER=local first).
"""
from alembic import op

revision = "024"
down_revision = "023"
branch_labels = None
depends_on = None

_TABLE = "endpoint_embeddings"
_COL = "embedding"
_HNSW_IDX = "idx_endpoint_embeddings_hnsw"


def upgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {_HNSW_IDX}")
    op.execute(f"TRUNCATE TABLE {_TABLE}")
    op.execute(f"ALTER TABLE {_TABLE} DROP COLUMN {_COL}")
    op.execute(
        f"ALTER TABLE {_TABLE} "
        f"ADD COLUMN {_COL} vector(1024) NOT NULL "
        f"DEFAULT array_fill(0, ARRAY[1024])::vector"
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


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {_HNSW_IDX}")
    op.execute(f"TRUNCATE TABLE {_TABLE}")
    op.execute(f"ALTER TABLE {_TABLE} DROP COLUMN {_COL}")
    op.execute(
        f"ALTER TABLE {_TABLE} "
        f"ADD COLUMN {_COL} vector(384) NOT NULL "
        f"DEFAULT array_fill(0, ARRAY[384])::vector"
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
