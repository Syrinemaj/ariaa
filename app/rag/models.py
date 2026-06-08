from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class EndpointSearchResult(BaseModel):
    endpoint_id: str
    method: str
    path: str
    canonical_key: str
    business_domain: Optional[str] = None
    business_action: Optional[str] = None
    score: float
    embedding_text: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SemanticSearchRequest(BaseModel):
    query: str
    run_id: Optional[str] = None
    top_k: int = 5
    score_threshold: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Minimum similarity score (0–1). Results below this value are dropped. "
                    "Recommended: 0.5 for production use to avoid false matches.",
    )


class SemanticSearchResponse(BaseModel):
    query: str
    results: List[EndpointSearchResult]
