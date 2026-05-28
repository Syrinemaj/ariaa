"""Tests for Fix 3.3 — Redis-backed circuit breaker."""
import time
from unittest.mock import MagicMock

import pytest

from app.resilience.circuit_breaker import (
    CircuitBreakerRegistry,
    RedisCircuitBreakerRegistry,
)


# ─── In-memory circuit breaker (regression tests) ────────────────────────────

class TestInMemoryCircuitBreaker:
    def test_initially_closed(self):
        cb = CircuitBreakerRegistry()
        assert cb.is_open("ep:GET /users") is False

    def test_opens_after_threshold(self):
        cb = CircuitBreakerRegistry()
        for _ in range(5):
            cb.record_failure("ep")
        assert cb.is_open("ep") is True

    def test_success_resets_failures(self):
        cb = CircuitBreakerRegistry()
        for _ in range(4):
            cb.record_failure("ep")
        cb.record_success("ep")
        assert cb.is_open("ep") is False

    def test_auto_recovers_after_timeout(self):
        cb = CircuitBreakerRegistry()
        cb.RECOVERY_TIMEOUT_SECONDS = 0  # immediate recovery for test
        for _ in range(5):
            cb.record_failure("ep")
        assert cb.is_open("ep") is True
        time.sleep(0.01)
        # Next is_open call auto-resets (half-open)
        assert cb.is_open("ep") is False


# ─── Redis-backed circuit breaker ────────────────────────────────────────────

def _make_redis_mock():
    """Build a minimal in-memory dict mock that behaves like redis.Redis."""
    store: dict = {}

    mock = MagicMock()

    def hgetall(key):
        return dict(store.get(key, {}))

    def hincrby(key, field, amount):
        if key not in store:
            store[key] = {}
        current = int(store[key].get(field, 0))
        store[key][field] = str(current + amount)
        return current + amount

    def hset(key, mapping=None, **kwargs):
        if key not in store:
            store[key] = {}
        if mapping:
            store[key].update({k: str(v) for k, v in mapping.items()})

    def delete(key):
        store.pop(key, None)

    def expire(key, seconds):
        pass  # TTL not needed in unit tests

    mock.hgetall.side_effect = hgetall
    mock.hincrby.side_effect = hincrby
    mock.hset.side_effect = hset
    mock.delete.side_effect = delete
    mock.expire.side_effect = expire

    return mock


class TestRedisCircuitBreaker:
    def _make_cb(self):
        return RedisCircuitBreakerRegistry(_make_redis_mock())

    def test_initially_closed(self):
        cb = self._make_cb()
        assert cb.is_open("ep") is False

    def test_opens_after_threshold(self):
        cb = self._make_cb()
        for _ in range(5):
            cb.record_failure("ep")
        assert cb.is_open("ep") is True

    def test_success_resets(self):
        cb = self._make_cb()
        for _ in range(5):
            cb.record_failure("ep")
        cb.record_success("ep")
        assert cb.is_open("ep") is False

    def test_partial_failures_not_open(self):
        cb = self._make_cb()
        for _ in range(4):
            cb.record_failure("ep")
        assert cb.is_open("ep") is False

    def test_auto_recovers_after_timeout(self):
        cb = self._make_cb()
        cb.RECOVERY_TIMEOUT_SECONDS = 0  # immediate recovery

        for _ in range(5):
            cb.record_failure("ep")
        assert cb.is_open("ep") is True

        # Force opened_at to be old
        redis = cb._redis
        old_data = redis.hgetall(cb._key("ep"))
        redis.hset(cb._key("ep"), mapping={"is_open": "1", "opened_at": "0"})

        assert cb.is_open("ep") is False  # auto-reset

    def test_multiple_endpoints_isolated(self):
        cb = self._make_cb()
        for _ in range(5):
            cb.record_failure("ep-A")
        assert cb.is_open("ep-A") is True
        assert cb.is_open("ep-B") is False

    def test_redis_call_uses_hset_on_threshold(self):
        """Verify is_open=1 is set in the hash when threshold reached."""
        redis_mock = _make_redis_mock()
        cb = RedisCircuitBreakerRegistry(redis_mock)
        for _ in range(5):
            cb.record_failure("ep")
        data = redis_mock.hgetall(cb._key("ep"))
        assert data.get("is_open") == "1"
