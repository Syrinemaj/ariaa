"""
Vector store — async SQLAlchemy.

Content-addressed cache:
  If the embedding text for an endpoint has not changed, the existing vector
  is reused without calling the embedding model (cost and latency saving).
  Cache key: sha256(embedding_text).

Embedding provider: LocalEmbeddingClient (BAAI/bge-small-en, 384 dims).
"""
from __future__ import annotations

import hashlib
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.rag.embeddings.builder import build_endpoint_embedding_text
from app.rag.embeddings.client import LocalEmbeddingClient
from app.models.embedding import EndpointEmbedding
from app.models.endpoint import Endpoint


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


async def index_endpoint_embedding(
    db: AsyncSession,
    endpoint: Endpoint,
    client: LocalEmbeddingClient,
) -> EndpointEmbedding:
    """
    Generate or update the embedding for a single endpoint.
    Cache hit (same text hash) → no model call.
    """
    embedding_text = build_endpoint_embedding_text(endpoint)
    text_hash = _content_hash(embedding_text)

    result = await db.execute(
        select(EndpointEmbedding).where(EndpointEmbedding.endpoint_id == endpoint.id)
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing_hash = _content_hash(existing.embedding_text)
        if existing_hash == text_hash:
            return existing  # cache hit — no model call

        embedding = await client.create_embedding_async(embedding_text)
        existing.embedding_text = embedding_text
        existing.embedding = embedding
        existing.metadata_json = _meta(endpoint)
        await db.flush()
        await db.refresh(existing)
        return existing

    embedding = await client.create_embedding_async(embedding_text)
    record = EndpointEmbedding(
        endpoint_id=endpoint.id,
        embedding_text=embedding_text,
        embedding=embedding,
        metadata_json=_meta(endpoint),
    )
    db.add(record)
    await db.flush()
    await db.refresh(record)
    return record


async def index_embeddings_for_run(
    db: AsyncSession,
    run_id: str,
    client: LocalEmbeddingClient,
) -> List[EndpointEmbedding]:
    # selectinload ensures endpoint.schema is loaded before the loop starts,
    # avoiding lazy-load in an async context (MissingGreenlet error).
    result = await db.execute(
        select(Endpoint)
        .options(selectinload(Endpoint.schema))
        .where(Endpoint.run_id == run_id)
    )
    endpoints = list(result.scalars().all())
    indexed = []
    for ep in endpoints:
        record = await index_endpoint_embedding(db=db, endpoint=ep, client=client)
        indexed.append(record)
    return indexed


def _meta(endpoint: Endpoint) -> dict:
    return {
        "canonical_key": endpoint.canonical_key,
        "method": endpoint.method,
        "path": endpoint.path,
        "business_domain": endpoint.business_domain,
        "business_action": endpoint.business_action,
    }
