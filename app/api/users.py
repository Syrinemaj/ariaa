from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit.events import AuditEvent
from app.audit.service import log_audit_event
from app.auth.dependencies import require_admin
from app.auth.schemas import CreateUserRequest, CurrentUserResponse
from app.auth.service import create_user
from app.auth.token_store import increment_token_version
from app.db.session import get_db
from app.models.user import User, UserRole

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("", response_model=dict)
async def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    users = (
        db.query(User)
        .filter(User.org_id == current_user.org_id)
        .order_by(User.created_at.desc())
        .all()
    )

    return {
        "users": [
            CurrentUserResponse(
                id=u.id,
                org_id=u.org_id,
                email=u.email,
                full_name=u.full_name,
                role=u.role,
                is_active=u.is_active,
            ).model_dump()
            for u in users
        ]
    }


@router.post("", response_model=CurrentUserResponse, status_code=status.HTTP_201_CREATED)
async def create_user_route(
    payload: CreateUserRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    try:
        user = create_user(
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

    log_audit_event(
        db=db,
        user=current_user,
        action=AuditEvent.USER_CREATED,
        resource_type="user",
        resource_id=user.id,
        metadata={"email": user.email, "role": user.role},
    )

    return CurrentUserResponse(
        id=user.id,
        org_id=user.org_id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
    )


@router.patch("/{user_id}/deactivate", response_model=CurrentUserResponse)
async def deactivate_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    user = (
        db.query(User)
        .filter(User.id == user_id, User.org_id == current_user.org_id)
        .first()
    )

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate your own account",
        )

    user.is_active = False
    user.updated_at = datetime.now(timezone.utc)
    db.commit()

    # Invalidate all existing access tokens for this user immediately
    increment_token_version(user.id)

    log_audit_event(
        db=db,
        user=current_user,
        action=AuditEvent.USER_DEACTIVATED,
        resource_type="user",
        resource_id=user.id,
        metadata={"target_email": user.email},
    )

    return CurrentUserResponse(
        id=user.id,
        org_id=user.org_id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
    )


@router.patch("/{user_id}/activate", response_model=CurrentUserResponse)
async def activate_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    user = (
        db.query(User)
        .filter(User.id == user_id, User.org_id == current_user.org_id)
        .first()
    )

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.is_active = True
    user.failed_login_count = 0
    user.locked_until = None
    user.updated_at = datetime.now(timezone.utc)
    db.commit()

    log_audit_event(
        db=db,
        user=current_user,
        action=AuditEvent.USER_ACTIVATED,
        resource_type="user",
        resource_id=user.id,
        metadata={"target_email": user.email},
    )

    return CurrentUserResponse(
        id=user.id,
        org_id=user.org_id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
    )
