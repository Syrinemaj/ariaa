"""
Unit tests — EmbeddingCache (Section 11.2).

EmbeddingCache is a Redis-only, content-addressed cache (see module
docstring in app/rag/embedding_cache.py): Redis hit -> return cached
embedding; Redis miss -> compute via ai_client and cache in Redis.
Persistent storage for real endpoints is a separate concern handled by
vector_store.index_endpoint_embedding(), not by this class.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from app.rag.embedding_cache import EmbeddingCache

FAKE_EMBEDDING = [0.1, 0.2, 0.3]


def _make_cache(redis_get=None, ai_result=None):
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=redis_get)
    redis.setex = AsyncMock()

    ai_client = AsyncMock()
    ai_client.create_embedding_async = AsyncMock(
        return_value=ai_result or FAKE_EMBEDDING
    )

    return EmbeddingCache(redis=redis, ai_client=ai_client)


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
        # AI client must NOT be called on a cache hit
        cache.ai_client.create_embedding_async.assert_not_called()


class TestCacheMiss:
    @pytest.mark.asyncio
    async def test_miss_calls_ai_and_caches_in_redis(self):
        cache = _make_cache(redis_get=None)
        result = await cache.get_or_create_embedding("POST", "/items", {})
        assert result == FAKE_EMBEDDING
        cache.ai_client.create_embedding_async.assert_called_once()
        cache.redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_miss_embeds_method_and_path(self):
        cache = _make_cache(redis_get=None)
        await cache.get_or_create_embedding("POST", "/items", {})
        cache.ai_client.create_embedding_async.assert_called_once_with("POST /items")
