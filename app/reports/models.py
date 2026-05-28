from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class StepLogReport(BaseModel):
    step_order: int
    method: str
    path: str
    status: str
    status_code: Optional[int] = None
    request_payload: Optional[Dict[str, Any]] = None
    response_payload: Optional[Any] = None
    error_message: Optional[str] = None


class AutomationExecutionReport(BaseModel):
    automation_run_id: str
    analysis_run_id: str
    instruction: str
    workflow_name: str
    status: str
    dry_run: bool
    total_steps: int
    success_count: int
    failed_count: int
    duration_seconds: float
    success_rate: float
    error_rate: float
    errors: List[StepLogReport] = Field(default_factory=list)
    logs: List[StepLogReport] = Field(default_factory=list)
    result: Dict[str, Any] = Field(default_factory=dict)


class AnalysisRunReport(BaseModel):
    analysis_run_id: str
    total_automation_runs: int
    total_steps: int
    total_success: int
    total_failed: int
    average_success_rate: float
