"""
Redis client factory — sync et async.

Clients disponibles :

get_redis()
  → redis.Redis synchrone (singleton, pool interne redis-py).
  Utilisé par : auth/dependencies.py, auth/token_store.py,
                workers/tasks/*, resilience/circuit_breaker.py

get_async_redis(request)
  → redis.asyncio.Redis depuis app.state.redis (pool configuré dans lifespan).
  Utilisé par : routes FastAPI async (api/jobs.py, api/bulk.py, etc.)
  Injecter via Depends(get_async_redis).

Fichiers qui utilisent ce module (ne jamais appeler redis.from_url() directement):
  - app/api/jobs.py                   → get_redis()
  - app/auth/dependencies.py          → get_redis()
  - app/auth/token_store.py           → get_redis()
  - app/bulk_execution/service.py     → get_redis()
  - app/workers/tasks/ingestion.py    → get_redis()
  - app/workers/tasks/execution.py    → get_redis()
  - app/resilience/circuit_breaker.py → get_redis() passé explicitement
"""
from __future__ import annotations

import redis
import redis.asyncio as aioredis
from fastapi import Request

from app.core.config import settings

# ─── Sync singleton (redis-py gère le pool en interne) ───────────────────────

_sync_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    """
    Process-level synchronous Redis singleton.
    redis-py's ConnectionPool handles thread-safety internally.
    Safe for Celery tasks and sync FastAPI dependencies.
    Uses REDIS_APP_URL (db index /2 by default).
    """
    global _sync_client
    if _sync_client is None:
        _sync_client = redis.from_url(
            settings.REDIS_APP_URL,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
            health_check_interval=30,
        )
    return _sync_client


# ─── Async pool (injecté via app.state dans main.py lifespan) ────────────────

async def get_async_redis(request: Request) -> aioredis.Redis:
    """
    FastAPI dependency — returns the shared async Redis client.
    The ConnectionPool (max_connections=20) is initialised in main.py lifespan.

    Usage:
        @router.get("/something")
        async def handler(redis: aioredis.Redis = Depends(get_async_redis)):
            await redis.get("key")
    """
    return request.app.state.redis
