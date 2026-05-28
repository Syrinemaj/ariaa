"""
Tâche Celery — indexation des embeddings pgvector.

Chaîne : process_har_pipeline → index_run_embeddings (automatique).
Cache content-addressed : si le texte d'un endpoint n'a pas changé,
l'embedding n'est pas re-généré (économie Azure OpenAI).
Déduplication : lock Redis sur run_id.
Queue : "embedding" (concurrency=1 — limité par les quotas Azure OpenAI).
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
    et les stocke dans pgvector.
    Utilise AsyncAzureOpenAI via le client singleton.
    """
    try:
        result = asyncio.run(_run_embedding_async(run_id=run_id))
        logger.info("Embedding indexing done for run=%s: %d vectors", run_id, result["indexed"])
        return result
    except Exception as exc:
        logger.error("Embedding task failed for run=%s: %s", run_id, exc)
        raise self.retry(exc=exc) if self.request.retries < self.max_retries else exc


async def _run_embedding_async(run_id: str) -> dict:
    from app.ai.azure_openai_client import AzureOpenAIClient
    from app.db.session import AsyncSessionLocal
    from app.rag.vector_store import index_embeddings_for_run

    client = AzureOpenAIClient()

    async with AsyncSessionLocal() as db:
        records = await index_embeddings_for_run(db=db, run_id=run_id, client=client)
        await db.commit()

    return {
        "run_id": run_id,
        "indexed": len(records),
    }
