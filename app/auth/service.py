"""
Auth service — async SQLAlchemy (AsyncSession).

Toutes les fonctions acceptent AsyncSession et utilisent
await db.execute(select(...)) à la place de db.query().

Celery tasks qui appellent ces fonctions doivent les wraper dans asyncio.run().
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import create_access_token
from app.auth.password import hash_password, verify_password
from app.core.config import settings
from app.models.organization import Organization
from app.models.user import User, UserRole

_MAX_FAILED_ATTEMPTS = 5
_LOCKOUT_MINUTES = 15


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(
        select(User).where(User.email == email.strip().lower())
    )
    return result.scalar_one_or_none()


async def create_user(
    db: AsyncSession,
    org_id: str,
    email: str,
    password: str,
    full_name: str,
    role: str = UserRole.OPERATOR.value,
) -> User:
    if role.upper() not in UserRole.values():
        raise ValueError("Invalid role")

    user = User(
        org_id=org_id,
        email=email.strip().lower(),
        full_name=full_name,
        hashed_password=hash_password(password),
        role=role.upper(),
        is_active=True,
    )

    db.add(user)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ValueError("User already exists")

    return user


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User | None:
    user = await get_user_by_email(db, email)

    if not user or not user.is_active:
        verify_password(password, "$2b$12$eImiTXuWVxfM37uY4JANjOe5XKjBKOGPNnfNQa0/LrJoKNg3QUuHS")
        return None

    if user.locked_until and user.locked_until > datetime.now(timezone.utc):
        return None

    if not verify_password(password, user.hashed_password):
        user.failed_login_count = (user.failed_login_count or 0) + 1
        if user.failed_login_count >= _MAX_FAILED_ATTEMPTS:
            user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=_LOCKOUT_MINUTES)
        await db.flush()
        return None

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = datetime.now(timezone.utc)
    await db.flush()

    return user


def create_token_for_user(user: User) -> str:
    return create_access_token(
        subject=user.id,
        email=user.email,
        role=user.role if isinstance(user.role, str) else user.role.value,
        org_id=user.org_id,
    )


async def get_or_create_default_org(db: AsyncSession) -> Organization:
    """
    INSERT ON CONFLICT DO NOTHING → race-safe org creation.
    """
    from uuid import uuid4

    stmt = (
        pg_insert(Organization)
        .values(id=str(uuid4()), name=settings.DEFAULT_ORG_NAME)
        .on_conflict_do_nothing(index_elements=["name"])
    )
    await db.execute(stmt)
    await db.flush()

    result = await db.execute(
        select(Organization).where(Organization.name == settings.DEFAULT_ORG_NAME)
    )
    return result.scalar_one()
