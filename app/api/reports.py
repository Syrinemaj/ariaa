from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import require_admin, require_admin_or_operator
from app.core.pagination import PaginationParams
from app.db.session import get_sync_db
from app.models.automation import AutomationRun
from app.models.user import User
from app.reports.service import (
    get_audit_logs_paginated,
    get_automation_report,
    get_automation_runs_paginated,
    get_daily_automation_trend,
    get_endpoints_risk,
    get_endpoints_summary,
    get_global_summary,
    get_kpi_trends,
    get_reports_for_analysis_run,
)
from app.security.tenancy import owner_visibility_clause
from app.teams.service import resolve_single_team_id_sync


class AutomationRunUpdateIn(BaseModel):
    workflow_name: Optional[str] = None

router = APIRouter(prefix="/reports", tags=["Reports"])


def _resolve_visibility(current_user: User, db: Session) -> tuple[Optional[str], Optional[str]]:
    """(owner_id, team_id) pair for report/run queries.
    ADMIN: (None, None) — unrestricted, sees the whole org.
    OPERATOR in exactly one team: (None, team_id) — team-wide, "members of a
    team see the same activity, analyzed by anyone in the team."
    OPERATOR in 0 or 2+ teams: (current_user.id, None) — own resources only,
    the pre-existing fallback (no single team to scope to)."""
    if current_user.role == "ADMIN":
        return None, None
    team_id = resolve_single_team_id_sync(db, current_user.id)
    if team_id:
        return None, team_id
    return current_user.id, None


@router.get("/automation/{automation_run_id}")
def get_automation_execution_report(
    automation_run_id: str,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin_or_operator),
):
    report = get_automation_report(db, automation_run_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Automation run not found")
    return report.model_dump()


@router.get("/run/{analysis_run_id}")
def get_analysis_run_report(
    analysis_run_id: str,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin_or_operator),
):
    owner_id, team_id = _resolve_visibility(current_user, db)
    return get_reports_for_analysis_run(
        db, analysis_run_id, org_id=current_user.org_id, owner_id=owner_id, team_id=team_id
    ).model_dump()


@router.get("/summary")
def get_summary(
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin_or_operator),
):
    owner_id, team_id = _resolve_visibility(current_user, db)
    return get_global_summary(db, org_id=current_user.org_id, owner_id=owner_id, team_id=team_id)


@router.get("/endpoints/summary")
def get_endpoints_summary_route(
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin_or_operator),
):
    owner_id, team_id = _resolve_visibility(current_user, db)
    return get_endpoints_summary(db, org_id=current_user.org_id, owner_id=owner_id, team_id=team_id)


@router.get("/endpoints/risk")
def get_endpoints_risk_route(
    limit: int = Query(default=5, ge=1, le=50),
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin_or_operator),
):
    owner_id, team_id = _resolve_visibility(current_user, db)
    return get_endpoints_risk(
        db, org_id=current_user.org_id, owner_id=owner_id, team_id=team_id, limit=limit
    )


@router.get("/kpi-trends")
def get_kpi_trends_route(
    window_days: int = Query(default=7, ge=1, le=90),
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin_or_operator),
):
    owner_id, team_id = _resolve_visibility(current_user, db)
    return get_kpi_trends(
        db, org_id=current_user.org_id, window_days=window_days, owner_id=owner_id, team_id=team_id
    )


@router.get("/daily")
def get_daily_trend(
    days: int = Query(default=30, ge=1, le=90),
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin_or_operator),
):
    owner_id, team_id = _resolve_visibility(current_user, db)
    return get_daily_automation_trend(
        db, org_id=current_user.org_id, days=days, owner_id=owner_id, team_id=team_id
    )


@router.get("/runs")
def list_automation_runs(
    analysis_run_id: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    source: Optional[str] = Query(default=None, description="'simple' or 'bulk'"),
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin_or_operator),
):
    owner_id, team_id = _resolve_visibility(current_user, db)
    return get_automation_runs_paginated(
        db=db,
        pagination=pagination,
        org_id=current_user.org_id,
        analysis_run_id=analysis_run_id,
        status=status,
        source=source,
        owner_id=owner_id,
        team_id=team_id,
    )


@router.patch("/automation-runs/{run_id}")
def update_automation_run(
    run_id: str,
    body: AutomationRunUpdateIn,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin_or_operator),
):
    run = db.query(AutomationRun).filter(
        AutomationRun.id == run_id,
        AutomationRun.org_id == current_user.org_id,
        owner_visibility_clause(AutomationRun, current_user),
    ).first()
    if not run:
        raise HTTPException(status_code=404, detail="Automation run not found")
    if current_user.role != "ADMIN" and run.created_by_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only modify your own automations")
    if body.workflow_name is not None:
        run.workflow_name = body.workflow_name.strip() or run.workflow_name
    db.commit()
    return {"id": run.id, "workflow_name": run.workflow_name}


@router.delete("/automation-runs/{run_id}", status_code=204)
def delete_automation_run(
    run_id: str,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin_or_operator),
):
    run = db.query(AutomationRun).filter(
        AutomationRun.id == run_id,
        AutomationRun.org_id == current_user.org_id,
        owner_visibility_clause(AutomationRun, current_user),
    ).first()
    if not run:
        raise HTTPException(status_code=404, detail="Automation run not found")
    if current_user.role != "ADMIN" and run.created_by_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only delete your own automations")
    db.delete(run)
    db.commit()


@router.get("/logs")
def list_audit_logs(
    action: Optional[str] = Query(default=None),
    resource_type: Optional[str] = Query(default=None),
    user_id: Optional[str] = Query(default=None),
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin),
):
    return get_audit_logs_paginated(
        db=db,
        pagination=pagination,
        org_id=current_user.org_id,
        action=action,
        resource_type=resource_type,
        user_id=user_id,
    )
