from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.approval.approval_service import approve_automation, create_approval_request
from app.audit.events import AuditEvent
from app.auth.dependencies import require_admin_or_operator
from app.db.session import get_sync_db
from app.models.approval import AutomationApproval
from app.models.automation import AutomationRun
from app.models.team_member import TeamMember
from app.models.user import User, UserRole
from app.security.tenancy import team_visibility_clause

router = APIRouter(prefix="/approvals", tags=["Approvals"])


class ApproveRequest(BaseModel):
    comment: str | None = None


class RejectRequest(BaseModel):
    comment: str | None = None


def _user_team_ids(db: Session, user_id: str) -> list:
    return [row[0] for row in db.query(TeamMember.team_id).filter(TeamMember.user_id == user_id).all()]


def _assert_run_owned(db: Session, automation_run_id: str, current_user: User) -> AutomationRun:
    run = db.query(AutomationRun).filter(
        AutomationRun.id == automation_run_id,
        AutomationRun.org_id == current_user.org_id,
        team_visibility_clause(AutomationRun, current_user, _user_team_ids(db, current_user.id)),
    ).first()
    if not run:
        raise HTTPException(status_code=404, detail="Automation run not found")
    return run


@router.get("")
def list_approvals(
    status: str = "pending",
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin_or_operator),
):
    # BUG-007: filter by org via join — operators must not see other orgs' approvals
    # (+ team scoping: operators only see their team's runs, plus unassigned ones)
    run_ids = [
        row.id
        for row in db.query(AutomationRun.id).filter(
            AutomationRun.org_id == current_user.org_id,
            team_visibility_clause(AutomationRun, current_user, _user_team_ids(db, current_user.id)),
        ).all()
    ]

    approvals = (
        db.query(AutomationApproval)
        .filter(
            AutomationApproval.status == status,
            AutomationApproval.automation_run_id.in_(run_ids),
        )
        .order_by(AutomationApproval.created_at.desc())
        .all()
    )

    result = []
    for a in approvals:
        run = db.query(AutomationRun).filter(AutomationRun.id == a.automation_run_id).first()
        result.append({
            "id": a.id,
            "automation_run_id": a.automation_run_id,
            "status": a.status,
            "approved_by": a.approved_by,
            "comment": a.comment,
            "approved_at": a.approved_at.isoformat() if a.approved_at else None,
            "created_at": a.created_at.isoformat(),
            "run": {
                "id": run.id,
                "workflow_name": run.workflow_name,
                "instruction": run.instruction,
                "dry_run": run.dry_run,
                "status": run.status,
                "total_steps": run.total_steps,
                "success_count": run.success_count,
                "failed_count": run.failed_count,
                "plan": run.plan_json,
            } if run else None,
        })

    return {"total": len(result), "items": result}


@router.post("/{automation_run_id}/approve")
def approve(
    automation_run_id: str,
    payload: ApproveRequest,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin_or_operator),
):
    # BUG-004: only admins may approve — operators cannot self-approve their own runs
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Only admin users can approve automation runs")

    # BUG-007: verify the run belongs to the caller's org
    _assert_run_owned(db, automation_run_id, current_user)

    result = approve_automation(
        db=db,
        automation_run_id=automation_run_id,
        approved_by=current_user.email,
        comment=payload.comment,
    )

    db.commit()
    return {"id": result.id, "status": result.status, "approved_by": result.approved_by}


@router.post("/{automation_run_id}/reject")
def reject(
    automation_run_id: str,
    payload: RejectRequest,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin_or_operator),
):
    # BUG-004: only admins may reject as well
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Only admin users can reject automation runs")

    # BUG-007: verify the run belongs to the caller's org
    _assert_run_owned(db, automation_run_id, current_user)

    approval = (
        db.query(AutomationApproval)
        .filter(AutomationApproval.automation_run_id == automation_run_id)
        .first()
    )
    if not approval:
        approval = create_approval_request(db=db, automation_run_id=automation_run_id)

    approval.status = "rejected"
    approval.approved_by = current_user.email
    approval.comment = payload.comment
    db.commit()
    db.refresh(approval)

    return {"id": approval.id, "status": approval.status, "approved_by": approval.approved_by}
