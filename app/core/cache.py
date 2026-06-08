"""
ARIACache — application-level Redis cache.

Three purpose-built cache layers to eliminate hot-path DB round-trips:

1. user:{id}            TTL 60 s   — user session data for get_current_user()
2. run_endpoints:{id}   no TTL     — endpoint list computed once per run
3. plan_validation:{h}  TTL 30 min — validated plan per (run_id, instruction)

Inject via Depends(get_aria_cache) in FastAPI route dependencies.
The underlying Redis pool is shared from app.state.redis (set up in lifespan).
"""
from __future__ import annotations

import hashlib
import json
from typing import Dict, List, Optional

import redis.asyncio as aioredis
from fastapi import Request


class ARIACache:
    def __init__(self, redis: aioredis.Redis) -> None:
        self.redis = redis

    # ── Layer 1: User session (TTL 60 s) ────────────────────────────────────

    async def get_user_session(self, user_id: str) -> Optional[Dict]:
        """Return cached user dict or None on miss."""
        raw = await self.redis.get(f"user:{user_id}")
        if raw:
            return json.loads(raw)
        return None

    async def set_user_session(self, user_id: str, user_data: Dict) -> None:
        """Cache user session for 60 seconds."""
        await self.redis.setex(f"user:{user_id}", 60, json.dumps(user_data))

    async def invalidate_user_session(self, user_id: str) -> None:
        """Evict user session on logout or role change."""
        await self.redis.delete(f"user:{user_id}")

    # ── Layer 2: Run endpoints (permanent until invalidated) ─────────────────

    async def get_run_endpoints(self, run_id: str) -> Optional[List[Dict]]:
        """Return cached endpoint list for a run or None on miss."""
        raw = await self.redis.get(f"run_endpoints:{run_id}")
        if raw:
            return json.loads(raw)
        return None

    async def set_run_endpoints(self, run_id: str, endpoints: List[Dict]) -> None:
        """Cache endpoint list permanently (until run is deleted/re-processed)."""
        await self.redis.set(f"run_endpoints:{run_id}", json.dumps(endpoints))

    async def invalidate_run(self, run_id: str) -> None:
        """Evict run endpoint cache when the run is reprocessed or deleted."""
        await self.redis.delete(f"run_endpoints:{run_id}")

    # ── Layer 3: Plan validation (TTL 30 min) ────────────────────────────────

    def _plan_key(self, run_id: str, instruction: str) -> str:
        digest = hashlib.sha256(
            f"{run_id}:{instruction}".encode()
        ).hexdigest()[:24]
        return f"plan_validation:{digest}"

    async def get_plan_validation(
        self, run_id: str, instruction: str
    ) -> Optional[Dict]:
        """Return a cached plan validation result or None on miss."""
        raw = await self.redis.get(self._plan_key(run_id, instruction))
        if raw:
            return json.loads(raw)
        return None

    async def set_plan_validation(
        self,
        run_id: str,
        instruction: str,
        result: Dict,
        ttl: int = 1800,
    ) -> None:
        """Cache a plan validation result for `ttl` seconds (default 30 min)."""
        await self.redis.setex(
            self._plan_key(run_id, instruction), ttl, json.dumps(result)
        )


def get_aria_cache(request: Request) -> ARIACache:
    """FastAPI dependency — returns a cache bound to the shared Redis pool."""
    return ARIACache(request.app.state.redis)
