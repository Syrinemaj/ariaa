from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base_client import EmbeddingClientProtocol
from app.db.json_safety import strip_wrapping_quotes
from app.models.endpoint import Endpoint
from app.rag.context_builder import build_rag_context
from app.rag.models import EndpointSearchResult
from app.rag.relevance_judge import verify_relevance_async
from app.rag.retriever import retrieve_relevant_endpoints
from app.rag.vector_store import index_embeddings_for_run


async def index_run_for_rag(
    db: AsyncSession,
    run_id: str,
    client: EmbeddingClientProtocol,
) -> list:
    return await index_embeddings_for_run(db=db, run_id=run_id, client=client)


async def search_rag_context(
    db: AsyncSession,
    query: str,
    client: EmbeddingClientProtocol,
    run_id: Optional[str] = None,
    org_id: Optional[str] = None,
    top_k: int = 5,
    score_threshold: float = 0.0,
    ai_client=None,
) -> Tuple[List[EndpointSearchResult], str]:
    """
    ai_client — optional AIClientProtocol instance. When provided, results
    with a low-confidence top score go through verify_relevance_async()
    (app/rag/relevance_judge.py) before being returned, to catch the case
    where embedding similarity finds "closest" endpoints in the right domain
    but none of them actually perform the requested action (e.g. "refresh
    the token" against an API with no refresh-token endpoint). Left as None
    for callers that already run their own post-RAG LLM filtering (e.g.
    plan_builder.py's generate_plan_selection) to avoid a redundant judge
    call on the same data.
    """
    results = await retrieve_relevant_endpoints(
        db=db,
        query=query,
        client=client,
        run_id=run_id,
        org_id=org_id,
        top_k=top_k,
        score_threshold=score_threshold,
    )
    if ai_client is not None:
        # db=None: `db` here is an AsyncSession, but structured_chat_async's
        # db param is a sync Session for cost logging — passing None makes
        # it open its own short-lived sync session internally instead
        # (app/ai/bedrock_client.py::_log_usage's ARIA-OBS-FIX path).
        results = await verify_relevance_async(query, results, ai_client, db=None)
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

        endpoint.business_domain = strip_wrapping_quotes(enrichment.get("business_domain"))
        endpoint.business_action = strip_wrapping_quotes(enrichment.get("business_action"))
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
