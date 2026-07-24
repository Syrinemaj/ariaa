from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.rag.embeddings.client import LocalEmbeddingClient
from app.models.endpoint import Endpoint
from app.rag.context_builder import build_rag_context
from app.rag.models import EndpointSearchResult
from app.rag.retriever import retrieve_relevant_endpoints
from app.rag.vector_store import index_embeddings_for_run


async def index_run_for_rag(
    db: AsyncSession,
    run_id: str,
    client: LocalEmbeddingClient,
) -> list:
    return await index_embeddings_for_run(db=db, run_id=run_id, client=client)


async def search_rag_context(
    db: AsyncSession,
    query: str,
    client: LocalEmbeddingClient,
    run_id: Optional[str] = None,
    org_id: Optional[str] = None,
    top_k: int = 5,
    score_threshold: float = 0.0,
) -> Tuple[List[EndpointSearchResult], str]:
    results = await retrieve_relevant_endpoints(
        db=db,
        query=query,
        client=client,
        run_id=run_id,
        org_id=org_id,
        top_k=top_k,
        score_threshold=score_threshold,
    )
    context = build_rag_context(results)
    return results, context


# ARIA-WORKFLOW-V2: supports the double-query RAG in plan_builder.py — one
# query for the instruction's direct intent, one for implicit dependency
# endpoints (setup/configuration/assign/notify). The same endpoint can
# legitimately surface in both; keep whichever match scored higher rather
# than counting/ordering it twice.
def merge_deduplicate(
    results_1: List[EndpointSearchResult],
    results_2: List[EndpointSearchResult],
) -> List[EndpointSearchResult]:
    """Merge two RAG result lists, deduplicated by endpoint_id (higher score
    wins), sorted by score descending."""
    best_by_id: Dict[str, EndpointSearchResult] = {}
    for result in [*results_1, *results_2]:
        existing = best_by_id.get(result.endpoint_id)
        if existing is None or result.score > existing.score:
            best_by_id[result.endpoint_id] = result
    return sorted(best_by_id.values(), key=lambda r: r.score, reverse=True)


async def enrich_endpoints_metadata(
    db: AsyncSession,
    run_id: str,
    enrichment_results: Dict[str, dict],
) -> int:
    updated = 0
    for endpoint_id, enrichment in enrichment_results.items():
        result = await db.execute(
            select(Endpoint).where(Endpoint.id == endpoint_id)
        )
        endpoint = result.scalar_one_or_none()
        if not endpoint:
            continue

        endpoint.business_domain = enrichment.get("business_domain")
        endpoint.business_action = enrichment.get("business_action")
        endpoint.metadata_json = {
            **(endpoint.metadata_json or {}),
            "ai_summary": enrichment.get("summary"),
            "ai_description": enrichment.get("description"),
            "ai_tags": enrichment.get("tags", []),
            "ai_confidence": enrichment.get("confidence"),
        }
        updated += 1

    await db.commit()
    return updated
