from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.events import AuditEvent
from app.audit.service import log_audit_event
from app.auth.dependencies import require_admin
from app.auth.schemas import CreateUserRequest
from app.auth.service import create_user
from app.auth.token_store import increment_token_version
from app.db.session import get_db
from app.models.analysis_run import AnalysisRun
from app.models.audit_log import AuditLog
from app.models.automation import AutomationRun
from app.models.connection import Connection, ConnectionOperator
from app.models.data_file import DataFile
from app.models.governance import ForbiddenEndpointRule, GovernancePolicy
from app.models.notification import Notification
from app.models.team_member import TeamMember
from app.models.user import User, UserRole

router = APIRouter(prefix="/users", tags=["Users"])


class RoleUpdateRequest(BaseModel):
    role: str


def _user_dict(u: User) -> dict:
    return {
        "id": u.id,
        "org_id": u.org_id,
        "email": u.email,
        "full_name": u.full_name,
        "role": u.role,
        "is_active": u.is_active,
        "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
    }


@router.get("", response_model=dict)
async def list_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    result = await db.execute(
        select(User)
        .where(User.org_id == current_user.org_id)
        .order_by(User.created_at.desc())
    )
    users = result.scalars().all()
    return {"users": [_user_dict(u) for u in users]}


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_user_route(
    payload: CreateUserRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    try:
        user = await create_user(
            db=db,
            org_id=current_user.org_id,
            email=payload.email,
            password=payload.password,
            full_name=payload.full_name,
            role=payload.role,
        )
    except ValueError as exc:
        detail = str(exc)
        http_status = status.HTTP_409_CONFLICT if "already exists" in detail else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=http_status, detail=detail)

    await log_audit_event(
        db=db,
        user=current_user,
        action=AuditEvent.USER_CREATED,
        resource_type="user",
        resource_id=user.id,
        metadata={"email": user.email, "role": user.role},
    )

    return _user_dict(user)


@router.patch("/{user_id}/role", response_model=dict)
async def update_user_role(
    user_id: str,
    payload: RoleUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if payload.role.upper() not in UserRole.values():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role. Accepted values: {', '.join(UserRole.values())}",
        )

    result = await db.execute(
        select(User).where(User.id == user_id, User.org_id == current_user.org_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot change your own role",
        )

    user.role = payload.role.upper()
    user.updated_at = datetime.now(timezone.utc)
    await db.flush()

    # Invalider les tokens existants pour que le nouveau rôle prenne effet immédiatement
    increment_token_version(user.id)

    await log_audit_event(
        db=db,
        user=current_user,
        action=AuditEvent.USER_CREATED,  # Reuse closest event; consider adding USER_ROLE_CHANGED
        resource_type="user",
        resource_id=user.id,
        metadata={"target_email": user.email, "new_role": user.role},
    )

    return _user_dict(user)


@router.patch("/{user_id}/deactivate", response_model=dict)
async def deactivate_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    result = await db.execute(
        select(User).where(User.id == user_id, User.org_id == current_user.org_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate your own account",
        )

    user.is_active = False
    user.updated_at = datetime.now(timezone.utc)
    await db.flush()

    increment_token_version(user.id)

    await log_audit_event(
        db=db,
        user=current_user,
        action=AuditEvent.USER_DEACTIVATED,
        resource_type="user",
        resource_id=user.id,
        metadata={"target_email": user.email},
    )

    return _user_dict(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_route(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Hard-deletes a deactivated account. Only allowed when is_active=False —
    an admin must deactivate first, which is also what revokes active
    sessions (increment_token_version), so there's no window where a
    logged-in session survives its own account's deletion.

    created_by_user_id / recipient_user_id / updated_by / created_by are
    plain FKs to users.id with no ondelete behavior — a bare DELETE would
    hit IntegrityError on the first referencing row. Historical records
    (analysis runs, automation runs, notifications, audit logs, connections,
    governance policy, forbidden-endpoint rules) are preserved and orphaned
    (actor set to NULL) rather than cascade-deleted; team_members and
    connection_operators have no nullable path (user_id is NOT NULL) so
    those assignment rows are removed outright. refresh_tokens already
    cascades at the DB level (ondelete="CASCADE", see
    app/models/refresh_token.py).
    """
    result = await db.execute(
        select(User).where(User.id == user_id, User.org_id == current_user.org_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account",
        )

    if user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only deactivated accounts can be deleted",
        )

    await db.execute(delete(TeamMember).where(TeamMember.user_id == user.id))
    # ConnectionOperator.user_id is NOT NULL (no nullable path like the others
    # below) — the assignment row itself must go, same as TeamMember above.
    await db.execute(delete(ConnectionOperator).where(ConnectionOperator.user_id == user.id))
    await db.execute(update(Connection).where(Connection.created_by == user.id).values(created_by=None))
    await db.execute(update(GovernancePolicy).where(GovernancePolicy.updated_by == user.id).values(updated_by=None))
    await db.execute(
        update(ForbiddenEndpointRule).where(ForbiddenEndpointRule.created_by == user.id).values(created_by=None)
    )
    await db.execute(update(AuditLog).where(AuditLog.user_id == user.id).values(user_id=None))
    await db.execute(
        update(Notification).where(Notification.recipient_user_id == user.id).values(recipient_user_id=None)
    )
    await db.execute(
        update(Notification).where(Notification.created_by_user_id == user.id).values(created_by_user_id=None)
    )
    await db.execute(
        update(AnalysisRun).where(AnalysisRun.created_by_user_id == user.id).values(created_by_user_id=None)
    )
    await db.execute(
        update(AutomationRun).where(AutomationRun.created_by_user_id == user.id).values(created_by_user_id=None)
    )
    await db.execute(
        update(DataFile).where(DataFile.created_by_user_id == user.id).values(created_by_user_id=None)
    )

    target_email = user.email
    await db.delete(user)
    await db.flush()

    await log_audit_event(
        db=db,
        user=current_user,
        action=AuditEvent.USER_DELETED,
        resource_type="user",
        resource_id=user_id,
        metadata={"target_email": target_email},
    )


@router.patch("/{user_id}/activate", response_model=dict)
async def activate_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    result = await db.execute(
        select(User).where(User.id == user_id, User.org_id == current_user.org_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.is_active = True
    user.failed_login_count = 0
    user.locked_until = None
    user.updated_at = datetime.now(timezone.utc)
    await db.flush()

    await log_audit_event(
        db=db,
        user=current_user,
        action=AuditEvent.USER_ACTIVATED,
        resource_type="user",
        resource_id=user.id,
        metadata={"target_email": user.email},
    )

    return _user_dict(user)
