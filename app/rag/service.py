from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.endpoint import Endpoint
from app.rag.context_builder import build_rag_context
from app.rag.models import EndpointSearchResult
from app.rag.retriever import retrieve_relevant_endpoints
from app.rag.vector_store import index_embeddings_for_run


def index_run_for_rag(db: Session, run_id: str):
    return index_embeddings_for_run(db=db, run_id=run_id)


def search_rag_context(
    db: Session,
    query: str,
    run_id: Optional[str] = None,
    top_k: int = 5,
) -> Tuple[List[EndpointSearchResult], str]:
    results = retrieve_relevant_endpoints(db=db, query=query, run_id=run_id, top_k=top_k)
    context = build_rag_context(results)
    return results, context


def enrich_endpoints_metadata(
    db: Session,
    run_id: str,
    enrichment_results: Dict[str, dict],
) -> int:
    updated = 0
    for endpoint_id, enrichment in enrichment_results.items():
        endpoint = db.query(Endpoint).filter(Endpoint.id == endpoint_id).first()
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

    db.commit()
    return updated
