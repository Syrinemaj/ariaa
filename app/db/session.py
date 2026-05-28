"""
Sessions SQLAlchemy — synchrone (Celery) et asynchrone (FastAPI).

Deux engines séparés :

  sync_engine  (psycopg2)
    → SessionLocal (sync)
    → Utilisé par Celery tasks (dans asyncio.run())
    → Utilisé par init_db (Base.metadata.create_all)

  async_engine (asyncpg)
    → AsyncSessionLocal (async)
    → Injecté dans les routes FastAPI via get_db()
    → pool_size=10, max_overflow=20

Pourquoi séparer ?
  Les drivers psycopg2 et asyncpg ne peuvent PAS partager le même engine.
  psycopg2 bloque le thread (adapté aux workers Celery).
  asyncpg ne bloque jamais le thread (adapté à FastAPI async).

Celery tasks :
  Utiliser SessionLocal directement, ou AsyncSessionLocal dans asyncio.run().
  NE PAS utiliser get_db() (qui est une dépendance FastAPI).
"""
from __future__ import annotations

import re
from typing import AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings


def _to_async_url(url: str) -> str:
    """Replace any postgresql driver prefix with asyncpg."""
    return re.sub(r"^postgresql(\+\w+)?://", "postgresql+asyncpg://", url)


def _to_sync_url(url: str) -> str:
    """Replace any postgresql driver prefix with psycopg2."""
    return re.sub(r"^postgresql(\+\w+)?://", "postgresql+psycopg2://", url)


# ─── Async engine (FastAPI routes) ───────────────────────────────────────────

async_engine = create_async_engine(
    _to_async_url(settings.DATABASE_URL),
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=False,
)

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,   # avoid lazy-load after commit in async context
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency — yields an AsyncSession.
    Commits on successful completion, rolls back on exception.

    Usage in routes:
        db: AsyncSession = Depends(get_db)
        result = await db.execute(select(User).where(User.id == uid))
        user = result.scalar_one_or_none()
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ─── Sync engine (Celery tasks + init_db) ────────────────────────────────────

sync_engine = create_engine(
    _to_sync_url(settings.DATABASE_URL),
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    pool_timeout=30,
    pool_recycle=3600,
)

SessionLocal: sessionmaker[Session] = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=sync_engine,
)

# Alias kept for backward compat with existing Celery task imports
engine = sync_engine
