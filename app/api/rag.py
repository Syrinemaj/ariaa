import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.ai.endpoint_understanding import enrich_endpoint_with_ai
from app.auth.dependencies import require_admin_or_operator
from app.db.session import get_db
from app.models.endpoint import Endpoint
from app.models.user import User
from app.rag.models import SemanticSearchRequest
from app.rag.service import enrich_endpoints_metadata, index_run_for_rag, search_rag_context
from app.registry.repository import get_run_by_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rag", tags=["RAG"])


@router.post("/index/{run_id}")
async def index_run_embeddings(
    run_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_operator),
):
    run = get_run_by_id(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Analysis run not found")

    indexed = index_run_for_rag(db=db, run_id=run_id)
    return {"run_id": run_id, "indexed_embeddings": len(indexed)}


@router.post("/search")
async def semantic_search(
    request: SemanticSearchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_operator),
):
    results, context = search_rag_context(
        db=db,
        query=request.query,
        run_id=request.run_id,
        top_k=request.top_k,
    )
    return {
        "query": request.query,
        "results": [result.model_dump() for result in results],
        "context": context,
    }


@router.post("/enrich/{run_id}")
async def enrich_run_endpoints(
    run_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_operator),
):
    run = get_run_by_id(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Analysis run not found")

    endpoints = db.query(Endpoint).filter(Endpoint.run_id == run_id).all()

    enrichment_results = {}
    for endpoint in endpoints:
        try:
            enrichment_results[endpoint.id] = enrich_endpoint_with_ai(endpoint)
        except Exception as e:
            logger.warning("Enrichment failed for endpoint %s: %s", endpoint.id, e)

    updated = enrich_endpoints_metadata(db=db, run_id=run_id, enrichment_results=enrichment_results)

    return {
        "run_id": run_id,
        "enriched_endpoints": updated,
        "results": enrichment_results,
    }
