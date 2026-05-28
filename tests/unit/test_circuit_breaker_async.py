"""Tests for Fix 7.1 — Async Redis circuit breaker with HALF_OPEN state."""
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.resilience.circuit_breaker import CircuitOpenError, RedisCircuitBreaker, RedisCircuitBreakerRegistry


def _make_async_redis_mock(initial_state: dict | None = None):
    """Build a simple async Redis mock backed by an in-memory dict."""
    store: dict = {}
    if initial_state:
        store.update(initial_state)

    mock = AsyncMock()

    async def hgetall(key):
        return dict(store.get(key, {}))

    async def hincrby(key, field, amount):
        store.setdefault(key, {})
        current = int(store[key].get(field, 0))
        store[key][field] = str(current + amount)
        return current + amount

    async def hset(key, mapping=None, **kwargs):
        store.setdefault(key, {})
        if mapping:
            store[key].update({k: str(v) for k, v in mapping.items()})

    async def hget(key, field):
        return store.get(key, {}).get(field)

    async def delete(key):
        store.pop(key, None)

    async def expire(key, seconds):
        pass

    mock.hgetall.side_effect = hgetall
    mock.hincrby.side_effect = hincrby
    mock.hset.side_effect = hset
    mock.hget.side_effect = hget
    mock.delete.side_effect = delete
    mock.expire.side_effect = expire

    return mock, store


class TestRedisCircuitBreakerStates:
    @pytest.mark.asyncio
    async def test_initially_closed_allows_requests(self):
        redis, _ = _make_async_redis_mock()
        cb = RedisCircuitBreaker(redis, "ep:GET /users", failure_threshold=5)
        assert await cb.is_request_allowed() is True
        assert await cb.get_state() == RedisCircuitBreaker.CLOSED

    @pytest.mark.asyncio
    async def test_opens_after_threshold(self):
        redis, _ = _make_async_redis_mock()
        cb = RedisCircuitBreaker(redis, "ep", failure_threshold=5)
        for _ in range(5):
            await cb.record_failure()
        assert await cb.get_state() == RedisCircuitBreaker.OPEN
        assert await cb.is_request_allowed() is False

    @pytest.mark.asyncio
    async def test_partial_failures_stay_closed(self):
        redis, _ = _make_async_redis_mock()
        cb = RedisCircuitBreaker(redis, "ep", failure_threshold=5)
        for _ in range(4):
            await cb.record_failure()
        assert await cb.get_state() == RedisCircuitBreaker.CLOSED
        assert await cb.is_request_allowed() is True

    @pytest.mark.asyncio
    async def test_success_resets_to_closed(self):
        redis, _ = _make_async_redis_mock()
        cb = RedisCircuitBreaker(redis, "ep", failure_threshold=5)
        for _ in range(5):
            await cb.record_failure()
        await cb.record_success()
        assert await cb.get_state() == RedisCircuitBreaker.CLOSED

    @pytest.mark.asyncio
    async def test_transitions_to_half_open_after_timeout(self):
        redis, store = _make_async_redis_mock()
        cb = RedisCircuitBreaker(redis, "ep", failure_threshold=5, recovery_timeout=0)

        for _ in range(5):
            await cb.record_failure()

        # Manually backdate opened_at to trigger HALF_OPEN
        store[cb._key]["state"] = RedisCircuitBreaker.OPEN
        store[cb._key]["opened_at"] = "0"  # epoch 0 = very old

        assert await cb.get_state() == RedisCircuitBreaker.HALF_OPEN

    @pytest.mark.asyncio
    async def test_half_open_allows_limited_calls(self):
        redis, store = _make_async_redis_mock()
        cb = RedisCircuitBreaker(redis, "ep", half_open_max_calls=3, recovery_timeout=0)

        # Force HALF_OPEN state
        store[cb._key] = {
            "state": RedisCircuitBreaker.HALF_OPEN,
            "half_open_calls": "0",
            "opened_at": "0",
        }

        assert await cb.is_request_allowed() is True   # call 1
        assert await cb.is_request_allowed() is True   # call 2
        assert await cb.is_request_allowed() is True   # call 3
        # 4th call exceeds max → re-open
        assert await cb.is_request_allowed() is False

    @pytest.mark.asyncio
    async def test_half_open_failure_reopens(self):
        redis, store = _make_async_redis_mock()
        cb = RedisCircuitBreaker(redis, "ep", failure_threshold=5, recovery_timeout=0)

        # Force HALF_OPEN
        store[cb._key] = {
            "state": RedisCircuitBreaker.HALF_OPEN,
            "half_open_calls": "1",
            "opened_at": "0",
        }

        await cb.record_failure()
        # Should be back to OPEN
        data = store[cb._key]
        assert data.get("state") == RedisCircuitBreaker.OPEN

    @pytest.mark.asyncio
    async def test_multiple_endpoints_isolated(self):
        redis, _ = _make_async_redis_mock()
        registry = RedisCircuitBreakerRegistry(redis, failure_threshold=5)
        for _ in range(5):
            await registry.record_failure("ep-A")
        assert await registry.is_open("ep-A") is True
        assert await registry.is_open("ep-B") is False
