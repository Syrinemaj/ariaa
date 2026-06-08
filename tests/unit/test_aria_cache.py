"""
Unit tests — ARIACache (Section 13.1).

Redis is mocked with an in-memory dict so tests run without infrastructure.
"""
from __future__ import annotations

import json
from typing import Dict, Optional
from unittest.mock import AsyncMock

import pytest

from app.core.cache import ARIACache


class FakeRedis:
    """In-memory Redis substitute for unit tests."""

    def __init__(self) -> None:
        self._store: Dict[str, bytes] = {}

    async def get(self, key: str) -> Optional[str]:
        value = self._store.get(key)
        return value.decode() if value else None

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self._store[key] = value.encode()

    async def set(self, key: str, value: str) -> None:
        self._store[key] = value.encode()

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)


def _cache() -> ARIACache:
    return ARIACache(FakeRedis())


# ── User session (Layer 1) ────────────────────────────────────────────────────

class TestUserSession:
    @pytest.mark.asyncio
    async def test_miss_returns_none(self):
        cache = _cache()
        assert await cache.get_user_session("u1") is None

    @pytest.mark.asyncio
    async def test_set_and_get_roundtrip(self):
        cache = _cache()
        data = {"id": "u1", "email": "a@b.com", "role": "ADMIN"}
        await cache.set_user_session("u1", data)
        result = await cache.get_user_session("u1")
        assert result == data

    @pytest.mark.asyncio
    async def test_invalidate_removes_entry(self):
        cache = _cache()
        await cache.set_user_session("u1", {"id": "u1"})
        await cache.invalidate_user_session("u1")
        assert await cache.get_user_session("u1") is None


# ── Run endpoints (Layer 2) ───────────────────────────────────────────────────

class TestRunEndpoints:
    @pytest.mark.asyncio
    async def test_miss_returns_none(self):
        cache = _cache()
        assert await cache.get_run_endpoints("run-1") is None

    @pytest.mark.asyncio
    async def test_set_and_get_roundtrip(self):
        cache = _cache()
        endpoints = [{"id": "ep1", "method": "GET", "path": "/users"}]
        await cache.set_run_endpoints("run-1", endpoints)
        result = await cache.get_run_endpoints("run-1")
        assert result == endpoints

    @pytest.mark.asyncio
    async def test_invalidate_run_removes_entry(self):
        cache = _cache()
        await cache.set_run_endpoints("run-1", [{"id": "ep1"}])
        await cache.invalidate_run("run-1")
        assert await cache.get_run_endpoints("run-1") is None


# ── Plan validation (Layer 3) ─────────────────────────────────────────────────

class TestPlanValidation:
    @pytest.mark.asyncio
    async def test_miss_returns_none(self):
        cache = _cache()
        assert await cache.get_plan_validation("run-1", "create 10 users") is None

    @pytest.mark.asyncio
    async def test_set_and_get_roundtrip(self):
        cache = _cache()
        result = {"is_valid": True, "issues": []}
        await cache.set_plan_validation("run-1", "create 10 users", result)
        cached = await cache.get_plan_validation("run-1", "create 10 users")
        assert cached == result

    @pytest.mark.asyncio
    async def test_different_instructions_produce_different_keys(self):
        cache = _cache()
        await cache.set_plan_validation("run-1", "create 5 users", {"is_valid": True})
        await cache.set_plan_validation("run-1", "delete all users", {"is_valid": False})
        r1 = await cache.get_plan_validation("run-1", "create 5 users")
        r2 = await cache.get_plan_validation("run-1", "delete all users")
        assert r1 != r2

    @pytest.mark.asyncio
    async def test_different_run_ids_produce_different_keys(self):
        cache = _cache()
        await cache.set_plan_validation("run-A", "create users", {"x": 1})
        await cache.set_plan_validation("run-B", "create users", {"x": 2})
        rA = await cache.get_plan_validation("run-A", "create users")
        rB = await cache.get_plan_validation("run-B", "create users")
        assert rA != rB


# ── Key stability ─────────────────────────────────────────────────────────────

class TestPlanCacheKey:
    def test_same_inputs_produce_same_key(self):
        cache = _cache()
        k1 = cache._plan_key("run-1", "create users")
        k2 = cache._plan_key("run-1", "create users")
        assert k1 == k2

    def test_different_inputs_produce_different_keys(self):
        cache = _cache()
        k1 = cache._plan_key("run-1", "create users")
        k2 = cache._plan_key("run-1", "delete users")
        assert k1 != k2
