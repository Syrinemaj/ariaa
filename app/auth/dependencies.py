"""
FastAPI authentication dependencies — async SQLAlchemy.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import decode_access_token
from app.auth.token_store import is_jti_blocklisted
from app.db.redis_client import get_redis
from app.db.session import get_db
from app.models.user import User, UserRole


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: AsyncSession = Depends(get_db),
) -> User:
    try:
        payload = decode_access_token(token)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    user_id: str | None = payload.get("sub")
    jti: str | None = payload.get("jti")

    if not user_id or not jti:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    # JTI blocklist (explicit logout)
    if is_jti_blocklisted(jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
        )

    # Token version (bulk invalidation on role change / deactivation)
    redis = get_redis()
    raw_version = redis.get(f"token_version:{user_id}")
    current_version = int(raw_version) if raw_version is not None else 0
    if int(payload.get("token_version", 0)) < current_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been invalidated",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    return user


def require_roles(allowed_roles: list[UserRole]) -> Callable:
    allowed_values = {r.value for r in allowed_roles}

    async def dependency(current_user: User = Depends(get_current_user)) -> User:
        role_value = (
            current_user.role
            if isinstance(current_user.role, str)
            else current_user.role.value
        )
        if role_value not in allowed_values:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user

    return dependency


async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    role_value = (
        current_user.role
        if isinstance(current_user.role, str)
        else current_user.role.value
    )
    if role_value != UserRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )
    return current_user


async def require_admin_or_operator(current_user: User = Depends(get_current_user)) -> User:
    role_value = (
        current_user.role
        if isinstance(current_user.role, str)
        else current_user.role.value
    )
    if role_value not in {UserRole.ADMIN.value, UserRole.OPERATOR.value}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or operator role required",
        )
    return current_user
