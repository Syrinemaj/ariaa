import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin_or_operator),
):
    run = await get_run_by_id(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Analysis run not found")

    embedding_client = request.app.state.embedding_client
    indexed = await index_run_for_rag(db=db, run_id=run_id, client=embedding_client)
    return {"run_id": run_id, "indexed_embeddings": len(indexed)}


@router.post("/search")
async def semantic_search(
    body: SemanticSearchRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin_or_operator),
):
    embedding_client = request.app.state.embedding_client
    results, context = await search_rag_context(
        db=db,
        query=body.query,
        client=embedding_client,
        run_id=body.run_id,
        org_id=current_user.org_id,
        top_k=body.top_k,
        score_threshold=body.score_threshold,
    )
    return {
        "query": body.query,
        "results": [r.model_dump() for r in results],
        "context": context,
    }


@router.post("/enrich/{run_id}")
async def enrich_run_endpoints(
    run_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin_or_operator),
):
    run = await get_run_by_id(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Analysis run not found")

    result = await db.execute(
        select(Endpoint)
        .options(selectinload(Endpoint.schema))
        .where(Endpoint.run_id == run_id)
    )
    endpoints = list(result.scalars().all())

    ai_client = request.app.state.ai_client
    enrichment_results = {}
    for endpoint in endpoints:
        try:
            enrichment_results[endpoint.id] = enrich_endpoint_with_ai(
                endpoint, client=ai_client
            )
        except Exception as e:
            logger.warning("Enrichment failed for endpoint %s: %s", endpoint.id, e)

    updated = await enrich_endpoints_metadata(
        db=db,
        run_id=run_id,
        enrichment_results=enrichment_results,
    )

    # Re-index embeddings so the enriched metadata (business_domain, action)
    # is reflected in the vectors used for semantic search.
    if updated > 0:
        embedding_client = request.app.state.embedding_client
        await index_run_for_rag(db=db, run_id=run_id, client=embedding_client)

    return {
        "run_id": run_id,
        "enriched_endpoints": updated,
        "results": enrichment_results,
    }
