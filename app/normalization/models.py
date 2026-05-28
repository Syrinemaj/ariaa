from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class PathParameter(BaseModel):
    name: str
    raw_value: str
    type: str
    source: str = "rules"
    confidence: float = 1.0


class NormalizedEndpoint(BaseModel):
    method: str
    original_url: str
    original_path: str
    normalized_path: str

    path_parameters: List[PathParameter] = Field(default_factory=list)

    canonical_key: str

    status: Optional[int] = None
    mime_type: Optional[str] = None

    request_body: Optional[Any] = None
    response_body: Optional[Any] = None

    source_count: int = 1

    metadata: Dict[str, Any] = Field(default_factory=dict)
