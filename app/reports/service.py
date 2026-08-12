from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional

from sqlalchemy import func, or_

from sqlalchemy.orm import Session

from app.core.pagination import PaginationParams, build_paginated_response, paginate_query
from app.models.analysis_run import AnalysisRun
from app.models.audit_log import AuditLog
from app.models.automation import AutomationRun
from app.reports.execution_report import build_automation_report
from app.reports.metrics import compute_success_rate
from app.reports.models import AnalysisRunReport, AutomationExecutionReport


def _team_filter(model: Any, team_ids: Optional[List[str]]) -> Any:
    """None = unrestricted (ADMIN). A list (possibly empty) scopes to those
    team(s) plus unassigned/org-wide rows — mirrors
    app.security.tenancy.team_visibility_clause for the sync report queries."""
    if team_ids is None:
        return None
    if team_ids:
        return or_(model.team_id.in_(team_ids), model.team_id.is_(None))
    return model.team_id.is_(None)


def get_automation_report(db: Session, automation_run_id: str) -> Optional[AutomationExecutionReport]:
    return build_automation_report(db, automation_run_id)


def get_reports_for_analysis_run(
    db: Session,
    analysis_run_id: str,
    org_id: Optional[str] = None,
    team_ids: Optional[List[str]] = None,
) -> AnalysisRunReport:
    query = db.query(AutomationRun).filter(AutomationRun.analysis_run_id == analysis_run_id)
    if org_id:
        query = query.filter(AutomationRun.org_id == org_id)
    team_filter = _team_filter(AutomationRun, team_ids)
    if team_filter is not None:
        query = query.filter(team_filter)
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


def get_global_summary(db: Session, org_id: Optional[str] = None, team_ids: Optional[List[str]] = None) -> dict:
    query = db.query(AutomationRun)
    if org_id:
        query = query.filter(AutomationRun.org_id == org_id)
    team_filter = _team_filter(AutomationRun, team_ids)
    if team_filter is not None:
        query = query.filter(team_filter)
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


def get_daily_automation_trend(
    db: Session,
    org_id: Optional[str] = None,
    days: int = 30,
    team_ids: Optional[List[str]] = None,
) -> List[dict]:
    """Automation runs created per day, over the last `days` days (zero-filled)."""
    since = datetime.now(timezone.utc) - timedelta(days=days - 1)
    since_midnight = since.replace(hour=0, minute=0, second=0, microsecond=0)

    query = (
        db.query(
            func.date(AutomationRun.created_at).label("day"),
            func.count().label("count"),
        )
        .filter(AutomationRun.created_at >= since_midnight)
        .group_by(func.date(AutomationRun.created_at))
    )
    if org_id:
        query = query.filter(AutomationRun.org_id == org_id)
    team_filter = _team_filter(AutomationRun, team_ids)
    if team_filter is not None:
        query = query.filter(team_filter)

    counts_by_day = {str(row.day): row.count for row in query.all()}

    return [
        {
            "date": (since_midnight + timedelta(days=offset)).date().isoformat(),
            "count": counts_by_day.get(
                (since_midnight + timedelta(days=offset)).date().isoformat(), 0
            ),
        }
        for offset in range(days)
    ]


def get_kpi_trends(
    db: Session,
    org_id: Optional[str] = None,
    window_days: int = 7,
    team_ids: Optional[List[str]] = None,
) -> dict:
    """Dashboard KPIs for the current window vs the equivalent previous window."""
    now = datetime.now(timezone.utc)
    current_start = now - timedelta(days=window_days)
    previous_start = now - timedelta(days=window_days * 2)

    def analysis_window(start: datetime, end: datetime) -> dict:
        query = db.query(
            func.count(AnalysisRun.id).label("runs"),
            func.coalesce(func.sum(AnalysisRun.total_normalized_endpoints), 0).label("endpoints"),
        ).filter(AnalysisRun.created_at >= start, AnalysisRun.created_at < end)
        if org_id:
            query = query.filter(AnalysisRun.org_id == org_id)
        team_filter = _team_filter(AnalysisRun, team_ids)
        if team_filter is not None:
            query = query.filter(team_filter)
        row = query.one()
        return {"runs": row.runs, "endpoints": row.endpoints}

    def automation_window(start: datetime, end: datetime) -> dict:
        query = db.query(
            func.count(AutomationRun.id).label("runs"),
            func.coalesce(func.sum(AutomationRun.success_count), 0).label("success"),
            func.coalesce(func.sum(AutomationRun.total_steps), 0).label("steps"),
        ).filter(AutomationRun.created_at >= start, AutomationRun.created_at < end)
        if org_id:
            query = query.filter(AutomationRun.org_id == org_id)
        team_filter = _team_filter(AutomationRun, team_ids)
        if team_filter is not None:
            query = query.filter(team_filter)
        row = query.one()
        return {"runs": row.runs, "success": row.success, "steps": row.steps}

    a_current = analysis_window(current_start, now)
    a_previous = analysis_window(previous_start, current_start)
    au_current = automation_window(current_start, now)
    au_previous = automation_window(previous_start, current_start)

    return {
        "window_days": window_days,
        "analysis_runs": {"current": a_current["runs"], "previous": a_previous["runs"]},
        "endpoints_catalogued": {"current": a_current["endpoints"], "previous": a_previous["endpoints"]},
        "automation_runs": {"current": au_current["runs"], "previous": au_previous["runs"]},
        "global_success_rate": {
            "current": compute_success_rate(au_current["success"], au_current["steps"]),
            "previous": compute_success_rate(au_previous["success"], au_previous["steps"]),
        },
    }


def get_automation_runs_paginated(
    db: Session,
    pagination: PaginationParams,
    org_id: Optional[str] = None,
    analysis_run_id: Optional[str] = None,
    status: Optional[str] = None,
    team_ids: Optional[List[str]] = None,
) -> dict:
    query = db.query(AutomationRun).order_by(AutomationRun.created_at.desc())
    if org_id:
        query = query.filter(AutomationRun.org_id == org_id)
    team_filter = _team_filter(AutomationRun, team_ids)
    if team_filter is not None:
        query = query.filter(team_filter)
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
