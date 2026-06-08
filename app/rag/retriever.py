from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.local_embedding_client import LocalEmbeddingClient
from app.rag.models import EndpointSearchResult
from app.rag.semantic_search import semantic_search_endpoints


async def retrieve_relevant_endpoints(
    db: AsyncSession,
    query: str,
    client: LocalEmbeddingClient,
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
