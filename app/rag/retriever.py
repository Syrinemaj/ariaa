from typing import List, Optional

from sqlalchemy.orm import Session

from app.rag.models import EndpointSearchResult
from app.rag.semantic_search import semantic_search_endpoints


def retrieve_relevant_endpoints(
    db: Session,
    query: str,
    run_id: Optional[str] = None,
    top_k: int = 5,
) -> List[EndpointSearchResult]:
    return semantic_search_endpoints(db=db, query=query, run_id=run_id, top_k=top_k)
