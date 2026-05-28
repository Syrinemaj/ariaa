from fastapi import APIRouter, Depends, Query

from app.audit.events import AuditEvent
from app.audit.service import log_audit_event
from app.auth.dependencies import require_admin
from app.cleanup.service import run_upload_cleanup
from app.db.session import get_db
from app.models.user import User
from sqlalchemy.orm import Session

router = APIRouter(prefix="/maintenance", tags=["Maintenance"])


@router.post("/cleanup/uploads")
async def cleanup_uploads(
    dry_run: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    result = run_upload_cleanup(dry_run=dry_run)

    log_audit_event(
        db=db,
        user=current_user,
        action=AuditEvent.UPLOAD_CLEANUP_RUN,
        resource_type="upload_directory",
        metadata={
            "deleted_count": result.get("deleted_count", 0),
            "dry_run": dry_run,
        },
    )

    return result
