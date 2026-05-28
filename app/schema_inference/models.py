from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class InferredSchema(BaseModel):
    type: str = "object"
    properties: Dict[str, Any] = Field(default_factory=dict)
    required: List[str] = Field(default_factory=list)


class AuthInfo(BaseModel):
    auth_required: bool = False
    auth_type: Optional[str] = None
    location: Optional[str] = None
    header_name: Optional[str] = None
    cookie_name: Optional[str] = None
    confidence: float = 0.0


class EndpointSchemaResult(BaseModel):
    method: str
    path: str
    canonical_key: str

    request_schema: Optional[InferredSchema] = None
    response_schema: Optional[InferredSchema] = None

    status_codes: List[int] = Field(default_factory=list)
    auth: AuthInfo = Field(default_factory=AuthInfo)

    examples_count: int = 1
    metadata: Dict[str, Any] = Field(default_factory=dict)
