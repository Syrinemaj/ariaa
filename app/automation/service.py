from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app.automation.batch_processor import execute_plan_batch
from app.automation.models import AutomationExecutionRequest, AutomationExecutionResult
from app.models.automation import AutomationRun, AutomationStepLog
from app.monitoring.service import log_execution_completed, log_execution_started
from app.security.execution_guard import ExecutionGuardError, assert_execution_allowed
from app.security.sanitizer import sanitize_payload


async def execute_automation(
    db: Session,
    request: AutomationExecutionRequest,
    approval_granted: bool = False,
    org_id: str = "",
    created_by_user_id: Optional[str] = None,
) -> Tuple[AutomationRun, AutomationExecutionResult]:
    plan = request.plan

    assert_execution_allowed(
        plan=plan,
        dry_run=request.dry_run,
        approval_granted=approval_granted,
    )

    automation_run = AutomationRun(
        analysis_run_id=plan.run_id,
        instruction=plan.instruction,
        workflow_name=plan.workflow_name,
        dry_run=request.dry_run,
        status="running",
        total_steps=len(plan.steps),
        plan_json=plan.model_dump(),
        org_id=org_id,
        created_by_user_id=created_by_user_id,
    )
    db.add(automation_run)
    db.commit()
    db.refresh(automation_run)

    log_execution_started(automation_run_id=automation_run.id, dry_run=request.dry_run)

    sanitized_auth = sanitize_payload(request.auth_headers)
    sanitized_rows = [sanitize_payload(row) for row in request.input_rows]

    result = await execute_plan_batch(
        plan=plan,
        input_rows=sanitized_rows,
        base_url=request.base_url,
        auth_headers=sanitized_auth,
        dry_run=request.dry_run,
    )

    automation_run.status = result.status
    automation_run.success_count = result.success_count
    automation_run.failed_count = result.failed_count
    automation_run.total_steps = result.total_steps
    automation_run.duration_seconds = result.metadata.get("duration_seconds", 0.0)
    automation_run.result_json = result.model_dump()

    for step_result in result.results:
        log = AutomationStepLog(
            automation_run_id=automation_run.id,
            step_order=step_result.step_order,
            method=step_result.method,
            path=step_result.path,
            status=step_result.status,
            status_code=step_result.status_code,
            request_payload=sanitize_payload(step_result.request_payload),
            response_payload=sanitize_payload(step_result.response_payload)
            if isinstance(step_result.response_payload, dict)
            else {"value": str(step_result.response_payload)},
            error_message=step_result.error_message,
        )
        db.add(log)

    db.commit()
    db.refresh(automation_run)

    log_execution_completed(
        automation_run_id=automation_run.id,
        status=result.status,
        success_count=result.success_count,
        failed_count=result.failed_count,
    )

    return automation_run, result
