from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.audit.service import log_audit_event
from app.auth.dependencies import require_admin_or_operator
from app.automation.models import AutomationExecutionRequest
from app.automation.service import execute_automation
from app.db.session import get_db
from app.models.user import User, UserRole
from app.monitoring.service import log_plan_generated, log_plan_validated
from app.planner.models import AutomationPlan
from app.planner.service import create_plan_from_instruction
from app.registry.repository import get_run_by_id
from app.security.execution_guard import ExecutionGuardError
from app.security.ssrf_guard import validate_target_url

router = APIRouter(prefix="/automation", tags=["Automation"])


class CreatePlanRequest(BaseModel):
    run_id: str
    instruction: str
    top_k: int = 8


class ExecutePlanRequest(BaseModel):
    plan: AutomationPlan
    input_rows: List[Dict[str, Any]] = Field(default_factory=list)
    base_url: Optional[str] = None
    auth_headers: Dict[str, str] = Field(default_factory=dict)
    dry_run: bool = True
    approval_granted: bool = False


@router.post("/plan")
async def create_automation_plan(
    request: CreatePlanRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_operator),
):
    run = get_run_by_id(db, request.run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Analysis run not found")

    plan, validation = create_plan_from_instruction(
        db=db,
        run_id=request.run_id,
        instruction=request.instruction,
        top_k=request.top_k,
    )

    log_plan_generated(
        run_id=request.run_id,
        instruction=request.instruction,
        steps_count=len(plan.steps),
    )
    log_plan_validated(is_valid=validation.is_valid, issues_count=len(validation.issues))

    log_audit_event(
        db=db,
        user=current_user,
        action="AUTOMATION_PLAN_GENERATED",
        resource_type="analysis_run",
        resource_id=request.run_id,
        metadata={"instruction": request.instruction, "top_k": request.top_k},
    )

    return {
        "plan": plan.model_dump(),
        "validation": validation.model_dump(),
    }


@router.post("/execute")
async def execute_automation_plan(
    request: ExecutePlanRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_operator),
):
    if request.base_url:
        validate_target_url(request.base_url)

    if not request.dry_run and current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=403,
            detail="Only admin can run real execution.",
        )

    if not request.dry_run and not request.approval_granted:
        raise HTTPException(
            status_code=403,
            detail="Real execution requires explicit approval.",
        )

    execution_request = AutomationExecutionRequest(
        plan=request.plan,
        input_rows=request.input_rows,
        base_url=request.base_url,
        auth_headers=request.auth_headers,
        dry_run=request.dry_run,
    )

    try:
        automation_run, result = await execute_automation(
            db=db,
            request=execution_request,
            approval_granted=request.approval_granted,
            org_id=current_user.org_id,
            created_by_user_id=current_user.id,
        )
    except ExecutionGuardError as e:
        raise HTTPException(status_code=403, detail=str(e))

    log_audit_event(
        db=db,
        user=current_user,
        action="AUTOMATION_EXECUTED",
        resource_type="automation_run",
        resource_id=automation_run.id,
        metadata={"dry_run": request.dry_run, "status": result.status},
    )

    return {
        "automation_run_id": automation_run.id,
        "status": result.status,
        "dry_run": result.dry_run,
        "success_count": result.success_count,
        "failed_count": result.failed_count,
        "total_steps": result.total_steps,
        "result": result.model_dump(),
    }
