"""
Semantic search — async SQLAlchemy.

Cosine distance calculée UNE SEULE FOIS dans ORDER BY (pas deux fois).
L'ancien code recalculait la distance en Python après l'avoir obtenu via SQL.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.ai.azure_openai_client import AzureOpenAIClient
from app.models.embedding import EndpointEmbedding
from app.models.endpoint import Endpoint
from app.rag.models import EndpointSearchResult


async def semantic_search_endpoints(
    db: AsyncSession,
    query: str,
    client: AzureOpenAIClient,
    run_id: Optional[str] = None,
    top_k: int = 5,
) -> list[EndpointSearchResult]:
    """
    Recherche sémantique : embedding de la requête → cosine distance pgvector.

    Correction double-calcul :
    La distance cosine était calculée deux fois dans l'ancien code
    (dans ORDER BY ET en Python pour le score). Maintenant elle est
    calculée dans SQL uniquement — le résultat est réutilisé pour le score.
    """
    query_embedding = client.create_embedding(query)

    distance_expr = EndpointEmbedding.embedding.cosine_distance(query_embedding)

    stmt = (
        select(EndpointEmbedding, Endpoint, distance_expr.label("distance"))
        .join(Endpoint, EndpointEmbedding.endpoint_id == Endpoint.id)
        .order_by(distance_expr)
        .limit(top_k)
    )

    if run_id:
        stmt = stmt.where(Endpoint.run_id == run_id)

    result = await db.execute(stmt)
    rows = result.all()

    return [
        EndpointSearchResult(
            endpoint_id=endpoint.id,
            method=endpoint.method,
            path=endpoint.path,
            canonical_key=endpoint.canonical_key,
            business_domain=endpoint.business_domain,
            business_action=endpoint.business_action,
            score=max(0.0, 1.0 - float(distance)),
            embedding_text=embedding_record.embedding_text,
            metadata=endpoint.metadata_json or {},
        )
        for embedding_record, endpoint, distance in rows
    ]
