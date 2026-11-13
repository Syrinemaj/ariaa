"""
Semantic search — async SQLAlchemy, cosine distance via pgvector HNSW.

Embedding provider: settings.EMBEDDING_PROVIDER (see
app/ai/base_client.py::create_embedding_client() and
app/core/config.py::EMBEDDING_PROVIDER) — Cohere Embed Multilingual v3 via
Bedrock by default. Queries are embedded via create_embedding_query_async()
(the query-side method, which may differ from the document-side one — see
EmbeddingClientProtocol); documents are indexed via create_embedding_async().
The query is embedded asynchronously (thread-pool executor) so the event
loop is never blocked.
"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base_client import EmbeddingClientProtocol
from app.models.embedding import EndpointEmbedding
from app.models.endpoint import Endpoint
from app.rag.models import EndpointSearchResult


async def semantic_search_endpoints(
    db: AsyncSession,
    query: str,
    client: EmbeddingClientProtocol,
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


async def retrieve_relevant_endpoints(
    db: AsyncSession,
    query: str,
    client: EmbeddingClientProtocol,
    run_id: Optional[str] = None,
    org_id: Optional[str] = None,
    top_k: int = 5,
    score_threshold: float = 0.0,
) -> List[EndpointSearchResult]:
    return await semantic_search_endpoints(
        db=db,
        query=query,
        client=client,
        run_id=run_id,
        org_id=org_id,
        top_k=top_k,
        score_threshold=score_threshold,
    )
