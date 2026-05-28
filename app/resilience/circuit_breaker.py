"""
Circuit Breaker Redis-backed — async, partagé entre tous les workers.

Problème résolu :
  4 workers Celery / 4 uvicorn = 4 états en mémoire indépendants.
  Worker 1 ouvre le circuit → Workers 2/3/4 continuent d'appeler l'API morte.
  Solution : état stocké dans Redis → partagé atomiquement entre TOUS les workers.

Machines d'états :
  CLOSED ──(failures ≥ threshold)──→ OPEN
  OPEN ──(recovery_timeout dépassé)──→ HALF_OPEN
  HALF_OPEN ──(success)──────────────→ CLOSED
  HALF_OPEN ──(failure)──────────────→ OPEN
  HALF_OPEN ──(calls ≥ max_calls)───→ OPEN (pas encore décidé)

Redis hash : cb:{endpoint_key}
  state          : "closed" | "open" | "half_open"
  failures       : compteur de pannes consécutives
  opened_at      : timestamp epoch (float)
  half_open_calls: nombre d'appels en HALF_OPEN

Concurrence : Redis HINCRBY est atomique → pas de race condition entre workers.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


class RedisCircuitBreaker:
    """
    Circuit breaker async pour un endpoint spécifique.
    Une instance par (redis_client, endpoint_key).
    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(
        self,
        redis_client,                    # redis.asyncio.Redis OU redis.Redis
        endpoint_key: str,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        half_open_max_calls: int = 3,
        key_ttl: int = 300,
    ) -> None:
        self._redis = redis_client
        self._key = f"cb:{endpoint_key}"
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self._ttl = key_ttl

    # ── Async public API ──────────────────────────────────────────────────────

    async def get_state(self) -> str:
        """
        Lit l'état depuis Redis et applique la transition OPEN → HALF_OPEN
        si le recovery_timeout est dépassé.
        """
        data = await self._redis.hgetall(self._key)
        if not data:
            return self.CLOSED

        state = data.get("state", self.CLOSED)

        if state == self.OPEN:
            opened_at = float(data.get("opened_at", 0))
            if time.time() - opened_at >= self.recovery_timeout:
                await self._transition_to_half_open()
                return self.HALF_OPEN

        return state

    async def is_request_allowed(self) -> bool:
        """
        CLOSED    → True (laisse passer)
        OPEN      → False (bloque)
        HALF_OPEN → True si encore dans la limite half_open_max_calls, sinon False
        """
        state = await self.get_state()

        if state == self.CLOSED:
            return True

        if state == self.OPEN:
            return False

        # HALF_OPEN: allow up to max_calls probes
        half_open_calls = int(
            (await self._redis.hget(self._key, "half_open_calls")) or 0
        )
        if half_open_calls < self.half_open_max_calls:
            await self._redis.hincrby(self._key, "half_open_calls", 1)
            return True

        # Too many half-open calls without decision → re-open
        await self._set_open()
        return False

    async def record_success(self) -> None:
        """
        Réinitialise le circuit en CLOSED.
        En HALF_OPEN, une réussite confirme la récupération.
        """
        await self._redis.delete(self._key)
        logger.debug("Circuit breaker CLOSED: %s", self._key)

    async def record_failure(self) -> None:
        """
        Incrémente le compteur de pannes.
        Si failures ≥ threshold → ouvre le circuit.
        En HALF_OPEN → re-ouvre immédiatement.
        """
        state = await self.get_state()

        if state == self.HALF_OPEN:
            # Immediate re-open on failure during probe
            await self._set_open()
            logger.warning("Circuit breaker re-OPEN (half-open probe failed): %s", self._key)
            return

        failures = await self._redis.hincrby(self._key, "failures", 1)
        await self._redis.expire(self._key, self._ttl)

        if failures >= self.failure_threshold:
            await self._set_open()
            logger.warning(
                "Circuit breaker OPEN after %d failures: %s",
                failures, self._key,
            )

    # ── Internal transitions ──────────────────────────────────────────────────

    async def _set_open(self) -> None:
        await self._redis.hset(
            self._key,
            mapping={
                "state": self.OPEN,
                "opened_at": str(time.time()),
                "failures": str(self.failure_threshold),
                "half_open_calls": "0",
            },
        )
        await self._redis.expire(self._key, self._ttl)

    async def _transition_to_half_open(self) -> None:
        await self._redis.hset(
            self._key,
            mapping={
                "state": self.HALF_OPEN,
                "half_open_calls": "0",
            },
        )
        await self._redis.expire(self._key, self._ttl)
        logger.info("Circuit breaker HALF_OPEN: %s", self._key)


class RedisCircuitBreakerRegistry:
    """
    Factory et cache local d'instances RedisCircuitBreaker.

    État dans Redis (partagé entre workers).
    Instances Python en cache local (économie de mémoire, réutilisation).

    Usage dans une tâche async :
        registry = RedisCircuitBreakerRegistry(async_redis_client)
        cb = registry.get("org:GET /users")
        if not await cb.is_request_allowed():
            raise CircuitOpenError(...)
        try:
            response = await make_request(...)
            await cb.record_success()
        except Exception:
            await cb.record_failure()
            raise
    """

    def __init__(
        self,
        redis_client,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        half_open_max_calls: int = 3,
    ) -> None:
        self._redis = redis_client
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._half_open_max_calls = half_open_max_calls
        self._cache: dict[str, RedisCircuitBreaker] = {}

    def get(self, endpoint_key: str) -> RedisCircuitBreaker:
        """Return (and cache locally) a RedisCircuitBreaker for this endpoint."""
        if endpoint_key not in self._cache:
            self._cache[endpoint_key] = RedisCircuitBreaker(
                redis_client=self._redis,
                endpoint_key=endpoint_key,
                failure_threshold=self._failure_threshold,
                recovery_timeout=self._recovery_timeout,
                half_open_max_calls=self._half_open_max_calls,
            )
        return self._cache[endpoint_key]

    async def is_open(self, endpoint_key: str) -> bool:
        """Convenience method — matches old CircuitBreakerRegistry interface."""
        return not await self.get(endpoint_key).is_request_allowed()

    async def record_success(self, endpoint_key: str) -> None:
        await self.get(endpoint_key).record_success()

    async def record_failure(self, endpoint_key: str) -> None:
        await self.get(endpoint_key).record_failure()

    async def reset(self, endpoint_key: str) -> None:
        await self._redis.delete(f"cb:{endpoint_key}")
        self._cache.pop(endpoint_key, None)


class CircuitOpenError(Exception):
    """Raised when a circuit breaker blocks a request."""
