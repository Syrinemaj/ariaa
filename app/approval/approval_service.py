from datetime import datetime

from sqlalchemy.orm import Session

from app.models.approval import AutomationApproval


class ApprovalAlreadyProcessedError(Exception):
    """Levée quand approve/reject cible une approbation qui n'est plus 'pending'."""


def create_approval_request(db: Session, automation_run_id: str) -> AutomationApproval:
    approval = AutomationApproval(automation_run_id=automation_run_id, status="pending")
    db.add(approval)
    db.commit()
    db.refresh(approval)
    return approval


def approve_automation(
    db: Session,
    automation_run_id: str,
    approved_by: str,
    comment: str | None = None,
) -> AutomationApproval:
    approval = (
        db.query(AutomationApproval)
        .filter(AutomationApproval.automation_run_id == automation_run_id)
        .with_for_update()
        .first()
    )

    if not approval:
        approval = AutomationApproval(automation_run_id=automation_run_id)
        db.add(approval)
    elif approval.status != "pending":
        raise ApprovalAlreadyProcessedError(
            f"Approval for run {automation_run_id!r} already {approval.status!r}"
        )

    approval.status = "approved"
    approval.approved_by = approved_by
    approval.comment = comment
    approval.approved_at = datetime.utcnow()

    db.commit()
    db.refresh(approval)
    return approval
