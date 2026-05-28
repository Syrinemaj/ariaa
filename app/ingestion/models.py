from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class TrafficEntry(BaseModel):
    method: str
    url: str
    path: str

    status: Optional[int] = None
    mime_type: Optional[str] = None

    request_headers: Dict[str, str] = Field(default_factory=dict)
    response_headers: Dict[str, str] = Field(default_factory=dict)

    request_body: Optional[Any] = None
    response_body: Optional[Any] = None

    # scoring
    heuristic_score: float = 0.0
    payload_score: float = 0.0
    relevance_score: float = 0.0
    ai_score: Optional[float] = None

    # classification
    is_api_candidate: bool = False
    is_ambiguous: bool = False
    decision: Optional[str] = None
    reason: Optional[str] = None
    business_domain: Optional[str] = None
    business_action: Optional[str] = None
