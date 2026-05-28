from typing import List, Optional

from sqlalchemy.orm import Session

from app.core.pagination import PaginationParams, build_paginated_response, paginate_query
from app.models.audit_log import AuditLog
from app.models.automation import AutomationRun
from app.reports.execution_report import build_automation_report
from app.reports.metrics import compute_success_rate
from app.reports.models import AnalysisRunReport, AutomationExecutionReport


def get_automation_report(db: Session, automation_run_id: str) -> Optional[AutomationExecutionReport]:
    return build_automation_report(db, automation_run_id)


def get_reports_for_analysis_run(
    db: Session,
    analysis_run_id: str,
    org_id: Optional[str] = None,
) -> AnalysisRunReport:
    query = db.query(AutomationRun).filter(AutomationRun.analysis_run_id == analysis_run_id)
    if org_id:
        query = query.filter(AutomationRun.org_id == org_id)
    runs: List[AutomationRun] = query.all()

    total_steps = sum(r.total_steps for r in runs)
    total_success = sum(r.success_count for r in runs)
    total_failed = sum(r.failed_count for r in runs)

    return AnalysisRunReport(
        analysis_run_id=analysis_run_id,
        total_automation_runs=len(runs),
        total_steps=total_steps,
        total_success=total_success,
        total_failed=total_failed,
        average_success_rate=compute_success_rate(total_success, total_steps),
    )


def get_global_summary(db: Session, org_id: Optional[str] = None) -> dict:
    query = db.query(AutomationRun)
    if org_id:
        query = query.filter(AutomationRun.org_id == org_id)
    runs: List[AutomationRun] = query.all()

    total_runs = len(runs)
    total_steps = sum(r.total_steps for r in runs)
    total_success = sum(r.success_count for r in runs)
    total_failed = sum(r.failed_count for r in runs)
    dry_runs = sum(1 for r in runs if r.dry_run)
    real_runs = total_runs - dry_runs

    status_counts: dict = {}
    for r in runs:
        status_counts[r.status] = status_counts.get(r.status, 0) + 1

    return {
        "total_automation_runs": total_runs,
        "dry_runs": dry_runs,
        "real_runs": real_runs,
        "total_steps": total_steps,
        "total_success": total_success,
        "total_failed": total_failed,
        "global_success_rate": compute_success_rate(total_success, total_steps),
        "status_breakdown": status_counts,
    }


def get_automation_runs_paginated(
    db: Session,
    pagination: PaginationParams,
    org_id: Optional[str] = None,
    analysis_run_id: Optional[str] = None,
    status: Optional[str] = None,
) -> dict:
    query = db.query(AutomationRun).order_by(AutomationRun.created_at.desc())
    if org_id:
        query = query.filter(AutomationRun.org_id == org_id)
    if analysis_run_id:
        query = query.filter(AutomationRun.analysis_run_id == analysis_run_id)
    if status:
        query = query.filter(AutomationRun.status == status)

    items, total = paginate_query(query, pagination)
    serialized = [
        {
            "id": r.id,
            "workflow_name": r.workflow_name,
            "instruction": r.instruction,
            "dry_run": r.dry_run,
            "status": r.status,
            "total_steps": r.total_steps,
            "success_count": r.success_count,
            "failed_count": r.failed_count,
            "duration_seconds": r.duration_seconds,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in items
    ]
    return build_paginated_response(serialized, total, pagination)


def get_audit_logs_paginated(
    db: Session,
    pagination: PaginationParams,
    org_id: str,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
) -> dict:
    query = (
        db.query(AuditLog)
        .filter(AuditLog.org_id == org_id)
        .order_by(AuditLog.created_at.desc())
    )
    if action:
        query = query.filter(AuditLog.action == action)
    if resource_type:
        query = query.filter(AuditLog.resource_type == resource_type)

    items, total = paginate_query(query, pagination)
    serialized = [
        {
            "id": r.id,
            "action": r.action,
            "resource_type": r.resource_type,
            "resource_id": r.resource_id,
            "user_id": r.user_id,
            "metadata": r.metadata_json,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in items
    ]
    return build_paginated_response(serialized, total, pagination)
