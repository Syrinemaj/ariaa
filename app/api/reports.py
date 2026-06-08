from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import require_admin, require_admin_or_operator
from app.core.pagination import PaginationParams
from app.db.session import get_sync_db
from app.models.user import User
from app.reports.service import (
    get_audit_logs_paginated,
    get_automation_report,
    get_automation_runs_paginated,
    get_global_summary,
    get_reports_for_analysis_run,
)

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
