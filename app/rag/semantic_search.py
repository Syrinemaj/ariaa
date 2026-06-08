"""
Semantic search — async SQLAlchemy, cosine distance via pgvector HNSW.

Embedding provider: LocalEmbeddingClient (BAAI/bge-small-en, 384 dims).
Queries are embedded with the BGE instruction prefix via
create_embedding_query_async(); documents are indexed without prefix.
The query is embedded asynchronously (thread-pool executor) so the event
loop is never blocked.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.local_embedding_client import LocalEmbeddingClient
from app.models.embedding import EndpointEmbedding
from app.models.endpoint import Endpoint
from app.rag.models import EndpointSearchResult


async def semantic_search_endpoints(
    db: AsyncSession,
    query: str,
    client: LocalEmbeddingClient,
    run_id: Optional[str] = None,
    org_id: Optional[str] = None,
    top_k: int = 5,
    score_threshold: float = 0.0,
) -> list[EndpointSearchResult]:
    """
    Embed the query, then retrieve the top_k most similar endpoints via
    cosine distance computed in PostgreSQL (single SQL round-trip).

    org_id is mandatory for multi-tenant isolation. When provided, search is
    restricted to endpoints belonging to that organisation, regardless of
    whether run_id is supplied.

    score_threshold filters out results whose similarity score is below the
    given value (default 0.0 = no filtering). Set to e.g. 0.5 to avoid
    returning low-confidence matches.
    """
    query_embedding = await client.create_embedding_query_async(query)

    distance_col = EndpointEmbedding.embedding.cosine_distance(
        query_embedding
    ).label("distance")

    stmt = (
        select(EndpointEmbedding, Endpoint, distance_col)
        .join(Endpoint, EndpointEmbedding.endpoint_id == Endpoint.id)
        .order_by(distance_col)
        .limit(top_k)
    )

    if run_id:
        stmt = stmt.where(Endpoint.run_id == run_id)

    if org_id:
        stmt = stmt.where(Endpoint.org_id == org_id)

    result = await db.execute(stmt)
    rows = result.all()

    results = []
    for embedding_record, endpoint, distance in rows:
        score = max(0.0, 1.0 - float(distance))
        if score < score_threshold:
            continue
        results.append(EndpointSearchResult(
            endpoint_id=endpoint.id,
            method=endpoint.method,
            path=endpoint.path,
            canonical_key=endpoint.canonical_key,
            business_domain=endpoint.business_domain,
            business_action=endpoint.business_action,
            score=score,
            embedding_text=embedding_record.embedding_text,
            metadata=endpoint.metadata_json or {},
        ))
    return results
