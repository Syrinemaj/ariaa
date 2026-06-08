"""
FastAPI authentication dependencies — async SQLAlchemy.

Fix 13.1: get_current_user() now checks ARIACache before hitting PostgreSQL.
User data is cached for 60 s with the key user:{id}. On cache hit, a detached
User instance is reconstructed without a DB round-trip. The JTI blocklist and
token-version checks still run on every request (they use Redis, not Postgres).
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import decode_access_token
from app.auth.token_store import is_jti_blocklisted
from app.core.cache import ARIACache, get_aria_cache
from app.db.redis_client import get_redis
from app.db.session import get_db
from app.models.user import User, UserRole


oauth2_scheme = HTTPBearer()


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(oauth2_scheme)],
    db: AsyncSession = Depends(get_db),
    cache: ARIACache = Depends(get_aria_cache),
) -> User:
    token = credentials.credentials
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

    # JTI blocklist check (explicit logout) — always validate, never cache
    if is_jti_blocklisted(jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
        )

    # Token version check (bulk invalidation on role change / deactivation)
    redis = get_redis()
    raw_version = redis.get(f"token_version:{user_id}")
    current_version = int(raw_version) if raw_version is not None else 0
    if int(payload.get("token_version", 0)) < current_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been invalidated",
        )

    # ── Cache-first user lookup ──────────────────────────────────────────────
    cached = await cache.get_user_session(user_id)
    if cached:
        if not cached.get("is_active", True):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive",
            )
        # Reconstruct a detached User for the request — no session needed.
        user = User(
            id=cached["id"],
            email=cached.get("email", ""),
            role=cached.get("role", ""),
            org_id=cached.get("org_id", ""),
            is_active=cached.get("is_active", True),
        )
        return user

    # ── DB lookup on cache miss ──────────────────────────────────────────────
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    await cache.set_user_session(user_id, {
        "id": user.id,
        "email": user.email,
        "role": user.role if isinstance(user.role, str) else user.role.value,
        "org_id": user.org_id,
        "is_active": user.is_active,
    })

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
