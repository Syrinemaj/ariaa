from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.planner.models import AutomationPlan


class AutomationExecutionRequest(BaseModel):
    plan: AutomationPlan
    input_rows: List[Dict[str, Any]] = Field(default_factory=list)
    base_url: Optional[str] = None
    auth_headers: Dict[str, str] = Field(default_factory=dict)
    dry_run: bool = True
    max_concurrency: int = 1


class StepExecutionResult(BaseModel):
    step_order: int
    method: str
    path: str
    url: Optional[str] = None
    status: str
    status_code: Optional[int] = None
    request_payload: Optional[Dict[str, Any]] = None
    response_payload: Optional[Any] = None
    error_message: Optional[str] = None


class AutomationExecutionResult(BaseModel):
    status: str
    dry_run: bool
    total_steps: int
    success_count: int
    failed_count: int
    results: List[StepExecutionResult] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
