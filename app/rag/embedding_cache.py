"""
Content-addressed embedding cache — Redis only (TTL 24 h).

Tier 1 : Redis (TTL 24 h) — sub-millisecond.
Tier 2 : LocalEmbeddingClient (BAAI/bge-small-en) — on Redis miss.

Persistent storage of embeddings for real endpoints is handled exclusively
by vector_store.index_endpoint_embedding(), which links each embedding to
a real endpoint row via a valid endpoint_id.

Cache key: SHA-256(method:path:json(schema, sorted)) — stable across HAR
files and runs, so the same logical endpoint observed in N different captures
maps to the same cache entry regardless of ingestion run.
"""
from __future__ import annotations

import hashlib
import json
from typing import List, Optional

import redis.asyncio as aioredis

from app.rag.embeddings.client import LocalEmbeddingClient

_REDIS_TTL_SECONDS: int = 86_400  # 24 hours


class EmbeddingCache:
    def __init__(
        self,
        redis: aioredis.Redis,
        ai_client: LocalEmbeddingClient,
    ) -> None:
        self.redis = redis
        self.ai_client = ai_client

    def _compute_content_hash(
        self, method: str, path: str, schema: dict
    ) -> str:
        content = f"{method}:{path}:{json.dumps(schema, sort_keys=True)}"
        return hashlib.sha256(content.encode()).hexdigest()

    async def _get_from_redis(self, content_hash: str) -> Optional[List[float]]:
        raw = await self.redis.get(f"emb:{content_hash}")
        if raw:
            return json.loads(raw)
        return None

    async def _cache_in_redis(
        self, content_hash: str, embedding: List[float]
    ) -> None:
        await self.redis.setex(
            f"emb:{content_hash}",
            _REDIS_TTL_SECONDS,
            json.dumps(embedding),
        )

    async def get_or_create_embedding(
        self, method: str, path: str, schema: dict
    ) -> List[float]:
        """
        Return a cached embedding or compute and cache a new one.

        For 100 endpoints seen across 10 HAR files, the first run computes
        100 embeddings; every subsequent run (within 24 h) makes 0 calls.
        """
        content_hash = self._compute_content_hash(method, path, schema)

        cached = await self._get_from_redis(content_hash)
        if cached is not None:
            return cached

        embedding = await self.ai_client.create_embedding_async(
            f"{method} {path}"
        )
        await self._cache_in_redis(content_hash, embedding)
        return embedding
