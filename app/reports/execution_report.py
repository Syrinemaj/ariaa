from sqlalchemy.orm import Session

from app.models.automation import AutomationRun, AutomationStepLog
from app.reports.metrics import compute_success_rate, compute_error_rate
from app.reports.models import AutomationExecutionReport, StepLogReport


def build_automation_report(db: Session, automation_run_id: str) -> AutomationExecutionReport | None:
    run: AutomationRun | None = db.query(AutomationRun).filter(AutomationRun.id == automation_run_id).first()
    if run is None:
        return None

    logs = db.query(AutomationStepLog).filter(
        AutomationStepLog.automation_run_id == automation_run_id
    ).order_by(AutomationStepLog.step_order).all()

    step_logs = [
        StepLogReport(
            step_order=log.step_order,
            method=log.method,
            path=log.path,
            status=log.status,
            status_code=log.status_code,
            request_payload=log.request_payload,
            response_payload=log.response_payload,
            error_message=log.error_message,
        )
        for log in logs
    ]

    failed_logs = [s for s in step_logs if s.status == "failed"]

    return AutomationExecutionReport(
        automation_run_id=run.id,
        analysis_run_id=run.analysis_run_id,
        instruction=run.instruction,
        workflow_name=run.workflow_name,
        status=run.status,
        dry_run=run.dry_run,
        total_steps=run.total_steps,
        success_count=run.success_count,
        failed_count=run.failed_count,
        duration_seconds=run.duration_seconds,
        success_rate=compute_success_rate(run.success_count, run.total_steps),
        error_rate=compute_error_rate(run.failed_count, run.total_steps),
        errors=failed_logs,
        logs=step_logs,
        result=run.result_json or {},
    )
