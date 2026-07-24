from sqlalchemy.orm import Session

from app.bulk_reports.batch_report import get_batch_summary
from app.bulk_reports.row_report import get_failed_rows
from app.models.automation import AutomationRun
from app.models.bulk_report import BulkExecutionReport


def build_bulk_report(db: Session, automation_run_id: str) -> dict:
    automation_run = (
        db.query(AutomationRun)
        .filter(AutomationRun.id == automation_run_id)
        .first()
    )

    if not automation_run:
        raise ValueError("Automation run not found")

    batch_summary = get_batch_summary(db=db, automation_run_id=automation_run_id)
    row_errors = get_failed_rows(db=db, automation_run_id=automation_run_id)

    # BUG-002: upsert — avoid creating N duplicate report records on repeated GETs
    report = db.query(BulkExecutionReport).filter(
        BulkExecutionReport.automation_run_id == automation_run_id
    ).first()

    if report:
        report.total_requested = automation_run.success_count + automation_run.failed_count
        report.success_count = automation_run.success_count
        report.failed_count = automation_run.failed_count
        report.duration_seconds = automation_run.duration_seconds
        report.status = automation_run.status
    else:
        report = BulkExecutionReport(
            automation_run_id=automation_run_id,
            total_requested=automation_run.success_count + automation_run.failed_count,
            success_count=automation_run.success_count,
            failed_count=automation_run.failed_count,
            partial_success_count=0,
            duration_seconds=automation_run.duration_seconds,
            row_errors=row_errors,
            batch_summary=batch_summary,
            status=automation_run.status,
        )
        db.add(report)

    db.commit()
    db.refresh(report)

    return {
        "bulk_report_id": report.id,
        "automation_run_id": automation_run_id,
        "status": report.status,
        "success_count": report.success_count,
        "failed_count": report.failed_count,
        "batch_summary": batch_summary,
        "row_errors": row_errors,
    }
