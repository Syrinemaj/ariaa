"""
LocalEmbeddingClient — sentence-transformers BAAI/bge-small-en, 384 dimensions.

Design decisions
----------------
- Singleton at class level: the SentenceTransformer model is loaded once per
  process and reused for all calls. Loading takes ~1 s and ~33 MB RAM.
- Lazy loading: the model is NOT loaded at import time. It loads on first
  embed() call so that importing this module in Celery workers that don't
  need embeddings has zero cost.
- Usable from both FastAPI (via app.state.embedding_client) and Celery workers
  (direct instantiation: LocalEmbeddingClient()). No dependency on app.state.
- Async interface: create_embedding_async() runs the sync encode() in the
  default thread-pool executor so it never blocks the asyncio event loop.

BGE query instruction
---------------------
BAAI/bge-small-en requires a task-specific instruction prefix on the **query**
side for retrieval/search tasks. Documents (indexed endpoints) are encoded
without any prefix; queries use:

    "Represent this sentence for searching relevant passages: <query>"

Use embed_query() / create_embedding_query_async() at search time.
Use embed() / create_embedding_async() for document/endpoint indexing.

Output dimensions: 384 (BAAI/bge-small-en native output, no padding).
"""
from __future__ import annotations

import asyncio
import logging
from typing import List

from app.core.config import settings

logger = logging.getLogger(__name__)

# Instruction prefix required by bge-small-en for retrieval queries.
# Documents (passage side) are encoded without any prefix.
_BGE_QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "


class LocalEmbeddingClient:
    """
    Wraps sentence-transformers with the same embedding interface as
    AzureOpenAIClient so call-sites need no changes beyond the type annotation.
    """

    _model = None  # class-level singleton — shared across all instances

    @classmethod
    def _get_model(cls):
        if cls._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                logger.info("local_embedding.model.loading model=%s", settings.LOCAL_EMBEDDING_MODEL)
                cls._model = SentenceTransformer(settings.LOCAL_EMBEDDING_MODEL)
                logger.info(
                    "local_embedding.model.ready model=%s dims=384",
                    settings.LOCAL_EMBEDDING_MODEL,
                )
            except Exception as exc:
                logger.error(
                    "local_embedding.model.load_failed model=%s error=%s",
                    settings.LOCAL_EMBEDDING_MODEL,
                    exc,
                )
                raise RuntimeError(
                    f"Failed to load sentence-transformers model "
                    f"'{settings.LOCAL_EMBEDDING_MODEL}': {exc}"
                ) from exc
        return cls._model

    # ── Document / indexing side (no prefix) ─────────────────────────────────

    def embed(self, text: str) -> List[float]:
        """Embed a single document/passage. Returns a list of 384 floats."""
        model = self._get_model()
        vector = model.encode(text, convert_to_numpy=True)
        return vector.tolist()

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Embed multiple documents in a single forward pass (more efficient)."""
        model = self._get_model()
        vectors = model.encode(texts, convert_to_numpy=True, batch_size=64)
        return [v.tolist() for v in vectors]

    # Alias used by existing vector_store / embedding_cache code
    def create_embedding(self, text: str) -> List[float]:
        return self.embed(text)

    async def create_embedding_async(self, text: str) -> List[float]:
        """Non-blocking async wrapper for document indexing (no BGE prefix)."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.embed, text)

    async def create_embedding_batch_async(self, texts: List[str]) -> List[List[float]]:
        """Non-blocking async wrapper for batch document indexing."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.embed_batch, texts)

    # ── Query / retrieval side (BGE instruction prefix) ───────────────────────

    def embed_query(self, query: str) -> List[float]:
        """
        Embed a search query with the BGE instruction prefix.
        Use this at search/retrieval time, not for document indexing.
        """
        return self.embed(_BGE_QUERY_INSTRUCTION + query)

    async def create_embedding_query_async(self, query: str) -> List[float]:
        """Non-blocking async wrapper for query embedding (with BGE prefix)."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.embed_query, query)
