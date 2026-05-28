from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.approval.approval_service import approve_automation, create_approval_request
from app.audit.events import AuditEvent
from app.audit.service import log_audit_event
from app.auth.dependencies import require_admin_or_operator
from app.db.session import get_db
from app.models.approval import AutomationApproval
from app.models.automation import AutomationRun
from app.models.user import User

router = APIRouter(prefix="/approvals", tags=["Approvals"])


class ApproveRequest(BaseModel):
    comment: str | None = None


class RejectRequest(BaseModel):
    comment: str | None = None


@router.get("")
def list_approvals(
    status: str = "pending",
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_operator),
):
    approvals = (
        db.query(AutomationApproval)
        .filter(AutomationApproval.status == status)
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
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_operator),
):
    result = approve_automation(
        db=db,
        automation_run_id=automation_run_id,
        approved_by=current_user.email,
        comment=payload.comment,
    )

    log_audit_event(
        db=db,
        user=current_user,
        action=AuditEvent.EXECUTION_APPROVED,
        resource_type="automation_run",
        resource_id=automation_run_id,
        metadata={"comment": payload.comment},
    )

    return {"id": result.id, "status": result.status, "approved_by": result.approved_by}


@router.post("/{automation_run_id}/reject")
def reject(
    automation_run_id: str,
    payload: RejectRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_operator),
):
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

    log_audit_event(
        db=db,
        user=current_user,
        action=AuditEvent.EXECUTION_REJECTED,
        resource_type="automation_run",
        resource_id=automation_run_id,
        metadata={"comment": payload.comment},
    )

    return {"id": approval.id, "status": approval.status, "approved_by": approval.approved_by}
