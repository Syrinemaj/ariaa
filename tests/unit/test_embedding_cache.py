"""
Unit tests — EmbeddingCache (Section 11.2).

All external dependencies (Redis, PostgreSQL, Azure OpenAI) are mocked.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.rag.embedding_cache import EmbeddingCache

FAKE_EMBEDDING = [0.1, 0.2, 0.3]
FAKE_HASH = "abc123"


def _make_cache(
    redis_get=None,
    redis_setex=AsyncMock(),
    redis_set=AsyncMock(),
    db_result=None,
    ai_result=None,
):
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=redis_get)
    redis.setex = redis_setex

    db = AsyncMock()
    scalar_mock = MagicMock()
    scalar_mock.embedding = FAKE_EMBEDDING if db_result else None
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = scalar_mock if db_result else None
    db.execute = AsyncMock(return_value=execute_result)
    db.add = MagicMock()
    db.flush = AsyncMock()

    ai_client = AsyncMock()
    ai_client.create_embedding_async = AsyncMock(
        return_value=ai_result or FAKE_EMBEDDING
    )

    return EmbeddingCache(redis=redis, db=db, ai_client=ai_client)


class TestContentHash:
    def test_same_inputs_produce_same_hash(self):
        cache = _make_cache()
        h1 = cache._compute_content_hash("GET", "/users", {"type": "str"})
        h2 = cache._compute_content_hash("GET", "/users", {"type": "str"})
        assert h1 == h2

    def test_different_schema_produces_different_hash(self):
        cache = _make_cache()
        h1 = cache._compute_content_hash("GET", "/users", {"type": "str"})
        h2 = cache._compute_content_hash("GET", "/users", {"type": "int"})
        assert h1 != h2

    def test_different_method_produces_different_hash(self):
        cache = _make_cache()
        h1 = cache._compute_content_hash("GET", "/users", {})
        h2 = cache._compute_content_hash("POST", "/users", {})
        assert h1 != h2

    def test_schema_key_order_does_not_matter(self):
        """JSON serialization is sorted so {"a":1,"b":2} == {"b":2,"a":1}."""
        cache = _make_cache()
        h1 = cache._compute_content_hash("GET", "/u", {"a": 1, "b": 2})
        h2 = cache._compute_content_hash("GET", "/u", {"b": 2, "a": 1})
        assert h1 == h2


class TestRedisHit:
    @pytest.mark.asyncio
    async def test_redis_hit_returns_cached_embedding(self):
        serialized = json.dumps(FAKE_EMBEDDING)
        cache = _make_cache(redis_get=serialized)
        result = await cache.get_or_create_embedding("GET", "/users", {})
        assert result == FAKE_EMBEDDING
        # DB and AI client must NOT be called
        cache.db.execute.assert_not_called()
        cache.ai_client.create_embedding_async.assert_not_called()


class TestDbHit:
    @pytest.mark.asyncio
    async def test_db_hit_warms_redis_and_returns_embedding(self):
        cache = _make_cache(redis_get=None, db_result=True)
        result = await cache.get_or_create_embedding("GET", "/users", {})
        assert result == FAKE_EMBEDDING
        # Redis must be warmed
        cache.redis.setex.assert_called_once()
        # AI client must NOT be called
        cache.ai_client.create_embedding_async.assert_not_called()


class TestCompleteMiss:
    @pytest.mark.asyncio
    async def test_complete_miss_calls_ai_and_saves_everywhere(self):
        cache = _make_cache(redis_get=None, db_result=False)
        result = await cache.get_or_create_embedding("POST", "/items", {})
        assert result == FAKE_EMBEDDING
        cache.ai_client.create_embedding_async.assert_called_once()
        # Must save to Redis
        cache.redis.setex.assert_called_once()
        # Must save to DB
        cache.db.add.assert_called_once()
        cache.db.flush.assert_called_once()
