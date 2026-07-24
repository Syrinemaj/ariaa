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
    get_global_summary,
    get_reports_for_analysis_run,
)


class AutomationRunUpdateIn(BaseModel):
    workflow_name: Optional[str] = None

router = APIRouter(prefix="/reports", tags=["Reports"])


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
    return get_reports_for_analysis_run(
        db, analysis_run_id, org_id=current_user.org_id
    ).model_dump()


@router.get("/summary")
def get_summary(
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin_or_operator),
):
    return get_global_summary(db, org_id=current_user.org_id)


@router.get("/daily")
def get_daily_trend(
    days: int = Query(default=30, ge=1, le=90),
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin_or_operator),
):
    return get_daily_automation_trend(db, org_id=current_user.org_id, days=days)


@router.get("/runs")
def list_automation_runs(
    analysis_run_id: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin_or_operator),
):
    return get_automation_runs_paginated(
        db=db,
        pagination=pagination,
        org_id=current_user.org_id,
        analysis_run_id=analysis_run_id,
        status=status,
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
    ).first()
    if not run:
        raise HTTPException(status_code=404, detail="Automation run not found")
    if current_user.role != "ADMIN" and run.created_by_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Vous ne pouvez modifier que vos propres automations")
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
    ).first()
    if not run:
        raise HTTPException(status_code=404, detail="Automation run not found")
    if current_user.role != "ADMIN" and run.created_by_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Vous ne pouvez supprimer que vos propres automations")
    db.delete(run)
    db.commit()


@router.get("/logs")
def list_audit_logs(
    action: Optional[str] = Query(default=None),
    resource_type: Optional[str] = Query(default=None),
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
    )
