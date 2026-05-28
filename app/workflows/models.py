from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class WorkflowStep(BaseModel):
    order: int
    method: str
    path: str
    canonical_key: str
    action: Optional[str] = None
    status: Optional[int] = None
    depends_on: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Workflow(BaseModel):
    name: str
    business_domain: Optional[str] = None
    steps: List[WorkflowStep] = Field(default_factory=list)
    confidence: float = 0.0
    metadata: Dict[str, Any] = Field(default_factory=dict)
