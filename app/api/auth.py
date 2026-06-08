"""
Auth routes — async SQLAlchemy.

/login   : authentifie + retourne access_token (15 min) + refresh_token (30j)
/refresh : échange un refresh_token contre un nouvel access_token
/logout  : révoque le refresh_token + met le JTI en blocklist Redis
/me      : retourne le profil de l'utilisateur courant
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.events import AuditEvent
from app.audit.service import log_audit_event
from app.auth.dependencies import get_current_user, oauth2_scheme
from app.auth.jwt import decode_access_token
from app.auth.schemas import (
    CurrentUserResponse,
    LoginRequest,
    RefreshRequest,
    TokenResponse,
)
from app.auth.service import authenticate_user, create_token_for_user, get_user_by_email
from app.auth.token_store import (
    blocklist_jti,
    create_refresh_token,
    rotate_refresh_token,
)
from app.core.config import settings
from app.core.rate_limit import limiter
from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login", response_model=TokenResponse)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def login(
    request: Request,
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    user = await authenticate_user(db=db, email=payload.email, password=payload.password)

    if not user:
        found_user = await get_user_by_email(db, payload.email)
        await _log_failed_login(db, found_user)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    refresh_raw = await create_refresh_token(
        db=db,
        user_id=user.id,
        ip_address=ip,
        user_agent=user_agent,
    )

    await log_audit_event(
        db=db,
        user=user,
        action=AuditEvent.USER_LOGIN,
        resource_type="user",
        resource_id=user.id,
        metadata={"role": user.role},
    )

    return TokenResponse(
        access_token=create_token_for_user(user),
        refresh_token=refresh_raw,
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    payload: RefreshRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    rotation_result = await rotate_refresh_token(
        db=db,
        old_raw=payload.refresh_token,
        ip_address=ip,
        user_agent=user_agent,
    )

    if rotation_result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    new_refresh_raw, user_id = rotation_result
    result = await db.execute(
        select(User).where(User.id == user_id, User.is_active == True)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    return TokenResponse(
        access_token=create_token_for_user(user),
        refresh_token=new_refresh_raw,
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    credentials: HTTPAuthorizationCredentials = Depends(oauth2_scheme),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        tok_payload = decode_access_token(credentials.credentials)
        jti = tok_payload.get("jti")
        exp = tok_payload.get("exp")
        if jti and exp:
            expires_at = datetime.fromtimestamp(exp, tz=timezone.utc)
            blocklist_jti(jti, expires_at)
    except ValueError:
        pass  # Token already invalid — logout still succeeds

    await log_audit_event(
        db=db,
        user=current_user,
        action=AuditEvent.USER_LOGOUT,
        resource_type="user",
        resource_id=current_user.id,
        metadata={},
    )


@router.get("/me", response_model=CurrentUserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return CurrentUserResponse(
        id=current_user.id,
        org_id=current_user.org_id,
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role,
        is_active=current_user.is_active,
    )


async def _log_failed_login(db: AsyncSession, user: User | None) -> None:
    audit = AuditLog(
        org_id=user.org_id if user else "unknown",
        user_id=user.id if user else None,
        action=AuditEvent.USER_LOGIN_FAILED,
        resource_type="user",
        resource_id=user.id if user else None,
        metadata_json={},
    )
    db.add(audit)
    await db.flush()
