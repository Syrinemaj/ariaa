"""
Vector store — async SQLAlchemy.

Cache content-addressed :
  Si le texte d'embedding n'a pas changé pour un endpoint,
  on ne rappelle pas Azure OpenAI (économie coût + latence).
  La clé de cache est sha256(embedding_text).
"""
from __future__ import annotations

import hashlib
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.azure_openai_client import AzureOpenAIClient
from app.ai.embeddings import build_endpoint_embedding_text
from app.models.embedding import EndpointEmbedding
from app.models.endpoint import Endpoint


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


async def index_endpoint_embedding(
    db: AsyncSession,
    endpoint: Endpoint,
    client: AzureOpenAIClient,
) -> EndpointEmbedding:
    """
    Génère ou met à jour l'embedding d'un endpoint.
    Cache content-addressed : skip si le texte n'a pas changé.
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
            return existing  # cache hit — no LLM call

        embedding = client.create_embedding(embedding_text)
        existing.embedding_text = embedding_text
        existing.embedding = embedding
        existing.metadata_json = _meta(endpoint)
        await db.flush()
        await db.refresh(existing)
        return existing

    embedding = client.create_embedding(embedding_text)
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
    client: AzureOpenAIClient,
) -> List[EndpointEmbedding]:
    result = await db.execute(
        select(Endpoint).where(Endpoint.run_id == run_id)
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
