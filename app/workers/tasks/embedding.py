"""
Tâche Celery — indexation des embeddings pgvector.

Chaîne : process_har_pipeline → index_run_embeddings (automatique).
Provider : LocalEmbeddingClient (BAAI/bge-small-en, 384 dims) — pas d'appel
           réseau, modèle chargé en mémoire dans le worker.
Cache content-addressed : si le texte d'un endpoint n'a pas changé,
l'embedding n'est pas re-généré.
Déduplication : lock Redis sur run_id.
Queue : "embedding" (concurrency=1 — CPU-bound, un seul modèle chargé).
"""
from __future__ import annotations

import asyncio
import logging

from app.workers.celery_app import celery_app
from app.workers.tasks.deduplication import deduplicated_task, embedding_key

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="aria.tasks.embedding.index_run_embeddings",
    queue="embedding",
    acks_late=True,
    reject_on_worker_lost=True,
    max_retries=3,
    default_retry_delay=60,
)
@deduplicated_task(key_fn=embedding_key, timeout_seconds=1800)
def index_run_embeddings(self, run_id: str, org_id: str) -> dict:
    """
    Génère les embeddings pour tous les endpoints d'un run_id
    et les stocke dans pgvector (384 dims, BAAI/bge-small-en).
    """
    try:
        result = asyncio.run(_run_embedding_async(run_id=run_id))
        logger.info("embedding.indexing.done run_id=%s indexed=%d", run_id, result["indexed"])
        return result
    except Exception as exc:
        logger.error("embedding.task.failed run_id=%s error=%s", run_id, exc)
        raise self.retry(exc=exc) if self.request.retries < self.max_retries else exc


async def _run_embedding_async(run_id: str) -> dict:
    import re

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.ai.local_embedding_client import LocalEmbeddingClient
    from app.core.config import settings
    from app.rag.vector_store import index_embeddings_for_run

    def _async_url(url: str) -> str:
        return re.sub(r"^postgresql(\+\w+)?://", "postgresql+asyncpg://", url)

    # Fresh engine per asyncio.run() call — avoids "Future attached to different loop"
    engine = create_async_engine(_async_url(settings.DATABASE_URL), pool_pre_ping=True)
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    # LocalEmbeddingClient is a class-level singleton — safe to instantiate here.
    client = LocalEmbeddingClient()

    try:
        async with session_factory() as db:
            records = await index_embeddings_for_run(db=db, run_id=run_id, client=client)
            await db.commit()
    finally:
        await engine.dispose()

    return {"run_id": run_id, "indexed": len(records)}
