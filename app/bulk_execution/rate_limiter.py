"""
Redis-backed rate limiter, shared across every Celery worker processing
batches of the same bulk job.

app/automation/rate_limiter.py's SimpleRateLimiter (a fixed per-instance
asyncio.sleep) is fine for the simple-execution path — one client, one
process, one run. It does not work here: a bulk job splits into
BULK_BATCH_SIZE-row batches, each its own Celery task, up to `concurrency`
of which run in parallel across worker processes (see
app/workers/celery_app.py). A SimpleRateLimiter instantiated per batch task
has zero visibility into what the other concurrent batches are doing — N
workers can each individually believe they're respecting a 0.1s delay while
collectively sending N requests/second against the target API.

Fixed-window counter via Redis INCR+EXPIRE — INCR is atomic, so concurrent
workers never race on the count. Not a token bucket (no smoothing across the
window boundary), but correct and simple, matching this codebase's existing
Redis usage style (see resilience/circuit_breaker.py for the same
INCR/atomic-primitive pattern applied to a different problem).
"""
from __future__ import annotations

import asyncio
import math


class RedisRateLimiter:
    def __init__(
        self,
        redis_client,          # redis.Redis (sync) — matches get_redis() usage
        job_id: str,           # scopes the limit to one bulk job; unrelated
                                # concurrent jobs don't throttle each other
        max_requests_per_second: float = 10.0,
    ) -> None:
        self._redis = redis_client
        self._key = f"ratelimit:bulk:{job_id}"
        self._max = max(1, math.floor(max_requests_per_second))
        self._retry_sleep = 1.0 / self._max

    async def wait(self) -> None:
        """Block until this call is within the current job's per-second
        budget. Never raises — a Redis error just lets the call through
        (fail open: a rate limiter must not be the reason a bulk run stalls
        entirely if Redis has a hiccup)."""
        while True:
            try:
                count = self._redis.incr(self._key)
                if count == 1:
                    self._redis.expire(self._key, 1)
            except Exception:
                return

            if count <= self._max:
                return

            await asyncio.sleep(self._retry_sleep)
