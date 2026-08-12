"""
Auth routes — async SQLAlchemy.

/login            : authentifie + retourne access_token (30 min) + refresh_token (30j)
/refresh          : échange un refresh_token contre un nouvel access_token
/logout           : révoque le refresh_token + met le JTI en blocklist Redis
/me               : retourne le profil de l'utilisateur courant
/forgot-password  : génère un token de réinitialisation et envoie un email
/reset-password   : vérifie le token et change le mot de passe
/request-access   : crée un compte en attente d'approbation (is_active=False)
"""
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.events import AuditEvent
from app.audit.service import log_audit_event
from app.auth.dependencies import get_current_user, oauth2_scheme
from app.auth.jwt import decode_access_token
from app.auth.password import hash_password, verify_password
from app.auth.schemas import (
    CurrentUserResponse,
    LoginRequest,
    RefreshRequest,
    TokenResponse,
)
from app.auth.service import (
    authenticate_user,
    create_token_for_user,
    get_or_create_default_org,
    get_user_by_email,
)
from app.auth.token_store import (
    blocklist_jti,
    create_refresh_token,
    increment_token_version,
    revoke_refresh_token,
    rotate_refresh_token,
)
from app.core.config import settings
from app.core.email import send_password_reset_email
from app.core.rate_limit import limiter
from app.db.redis_client import get_redis
from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.models.user import User, UserRole

router = APIRouter(prefix="/auth", tags=["Auth"])


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        return v


class RequestAccessRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        return v

    @field_validator("full_name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if len(v.strip()) < 2:
            raise ValueError("Name must be at least 2 characters long")
        return v.strip()


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

        # Si l'utilisateur existe mais est inactif et que le mot de passe est correct
        # → donner un message plus précis (sans révéler l'existence de l'email si mauvais mdp)
        if found_user and not found_user.is_active:
            if verify_password(payload.password, found_user.hashed_password):
                if not found_user.last_login_at:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Account pending approval",
                    )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Account deactivated",
                )

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
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def refresh(
    request: Request,
    payload: RefreshRequest,
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
    payload: LogoutRequest | None = None,
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

    if payload and payload.refresh_token:
        await revoke_refresh_token(db, payload.refresh_token)

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


@router.post("/forgot-password", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def forgot_password(
    request: Request,
    payload: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Génère un token de réinitialisation et envoie un email.
    Retourne toujours 204 pour éviter l'énumération d'utilisateurs.
    """
    user = await get_user_by_email(db, payload.email)
    if user and user.is_active:
        token = secrets.token_urlsafe(32)
        redis = get_redis()
        redis.setex(
            f"pwd_reset:{token}",
            settings.PASSWORD_RESET_TTL_SECONDS,
            user.id,
        )
        reset_link = f"{settings.FRONTEND_URL}/reset-password?token={token}"
        # Fire-and-forget — don't let SMTP errors block the response
        await send_password_reset_email(
            to=user.email,
            full_name=user.full_name,
            reset_link=reset_link,
        )


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(
    payload: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Vérifie le token et change le mot de passe.
    Le token est à usage unique et expire après PASSWORD_RESET_TTL_SECONDS.
    """
    redis = get_redis()
    user_id = redis.get(f"pwd_reset:{payload.token}")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired token. Please request a new one.",
        )

    result = await db.execute(
        select(User).where(User.id == user_id, User.is_active == True)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired token. Please request a new one.",
        )

    user.hashed_password = hash_password(payload.new_password)
    user.password_changed_at = datetime.now(timezone.utc)
    user.updated_at = datetime.now(timezone.utc)
    await db.flush()

    # Invalider tous les tokens existants (forcer re-login)
    increment_token_version(user.id)

    # Supprimer le token pour le rendre non réutilisable
    redis.delete(f"pwd_reset:{payload.token}")


@router.post("/request-access", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def request_access(
    request: Request,
    payload: RequestAccessRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Crée un compte en attente d'approbation (is_active=False).
    Un admin doit approuver via PATCH /users/{id}/activate.
    Retourne toujours 204 pour éviter l'énumération d'emails.
    """
    # Vérifier si l'email existe déjà (silencieux pour anti-énumération)
    existing = await get_user_by_email(db, payload.email)
    if existing:
        return  # Silencieux — ne pas révéler si l'email existe

    org = await get_or_create_default_org(db)

    user = User(
        org_id=org.id,
        email=payload.email.strip().lower(),
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role=UserRole.OPERATOR.value,
        is_active=False,  # En attente d'approbation admin
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()


async def _log_failed_login(db: AsyncSession, user: User | None) -> None:
    if not user:
        return  # No valid org_id — skip audit for unknown emails
    audit = AuditLog(
        org_id=user.org_id,
        user_id=user.id,
        action=AuditEvent.USER_LOGIN_FAILED,
        resource_type="user",
        resource_id=user.id,
        metadata_json={},
    )
    db.add(audit)
    await db.flush()
