from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.audit.service import list_audit_logs
from app.auth.dependencies import require_admin_or_operator
from app.db.session import get_db
from app.models.user import User

router = APIRouter(prefix="/audit-logs", tags=["Audit Logs"])


@router.get("")
async def get_audit_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_operator),
):
    return list_audit_logs(db=db, user=current_user, page=page, page_size=page_size)
