from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class BusinessIntent(BaseModel):
    instruction: str
    intent: str
    business_domain: Optional[str] = None
    quantity: Optional[int] = None
    entities: List[str] = Field(default_factory=list)
    action: str
    confidence: float = 0.0
    requires_bulk_execution: bool = False
    reason: Optional[str] = None


class PlanStep(BaseModel):
    order: int
    endpoint_id: str
    method: str
    path: str
    canonical_key: str
    action: Optional[str] = None
    business_domain: Optional[str] = None
    depends_on: List[str] = Field(default_factory=list)
    request_schema: Optional[Dict[str, Any]] = None
    response_schema: Optional[Dict[str, Any]] = None
    auth_required: bool = False
    risk_level: str = "low"


class AutomationPlan(BaseModel):
    run_id: str
    instruction: str
    intent: BusinessIntent
    workflow_name: str
    steps: List[PlanStep] = Field(default_factory=list)
    requires_approval: bool = True
    dry_run_default: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PlanValidationIssue(BaseModel):
    level: str
    message: str
    step_order: Optional[int] = None
    canonical_key: Optional[str] = None


class PlanValidationResult(BaseModel):
    is_valid: bool
    issues: List[PlanValidationIssue] = Field(default_factory=list)
