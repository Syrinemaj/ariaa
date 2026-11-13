"""
AI client protocols — structural subtyping via typing.Protocol.

Two protocols are defined:
  AIClientProtocol     — completion methods, implemented by BedrockClient
    (the only completion provider — see create_ai_client() below).
  EmbeddingClientProtocol — embedding methods, implemented by
    LocalEmbeddingClient and BedrockEmbeddingClient — see
    create_embedding_client() below.

GroqClient and AzureOpenAIClient used to be alternative implementations of
AIClientProtocol, selected via AI_PROVIDER, before the model-selection
evaluation (evaluation/aggregate.py) made Bedrock's cost/latency/reliability
case decisive enough to drop the other two providers rather than keep
maintaining three parallel implementations for two that were never used in
production. BedrockClient satisfies AIClientProtocol without inheriting from
it (duck typing / structural subtyping) — the Protocol stays, in case a
second provider is ever worth adding back, but only one implementation
exists today.

Embeddings moved to the same pattern (EMBEDDING_PROVIDER setting +
create_embedding_client() factory) when LocalEmbeddingClient
(BAAI/bge-small-en, English-only) was replaced by BedrockEmbeddingClient
(Cohere Embed Multilingual v3) as the default, for French/English
cross-lingual retrieval — see app/core/config.py::EMBEDDING_PROVIDER.

Usage in type annotations:
  def my_fn(client: AIClientProtocol) -> ...: ...
  def embed_fn(client: EmbeddingClientProtocol) -> ...: ...
"""
from __future__ import annotations

from typing import Any, List, Optional
from typing import runtime_checkable, Protocol

from sqlalchemy.orm import Session


class StructuredResponseError(Exception):
    """Raised when an LLM's structured_chat response doesn't satisfy the
    required schema fields even after a retry — see BedrockClient.structured_chat.
    Callers should catch this and surface a clean error, not a raw KeyError."""


@runtime_checkable
class AIClientProtocol(Protocol):
    """
    Completion client — implemented by BedrockClient.
    Embeddings are intentionally excluded: use EmbeddingClientProtocol.
    """

    def classify_api_call(
        self,
        payload: dict,
        db: Optional[Session] = None,
    ) -> Any:
        """Classify an HTTP call as business API or noise."""
        ...

    def structured_chat(
        self,
        system_prompt: str,
        user_payload: dict[str, Any],
        json_schema: dict[str, Any],
        task_name: str,
        db: Optional[Session],
    ) -> dict[str, Any]:
        """Synchronous structured JSON completion."""
        ...

    async def structured_chat_async(
        self,
        system_prompt: str,
        user_payload: dict[str, Any],
        json_schema: dict[str, Any],
        task_name: str,
        db: Optional[Session],
    ) -> dict[str, Any]:
        """Asynchronous structured JSON completion."""
        ...


@runtime_checkable
class EmbeddingClientProtocol(Protocol):
    """
    Embedding client — implemented by LocalEmbeddingClient and
    BedrockEmbeddingClient. Kept separate from AIClientProtocol because
    embedding and completion models are selected independently (see
    create_embedding_client() below).

    Declares the full surface real call sites depend on across app/rag/* —
    document side (embed/embed_batch/create_embedding*) and query side
    (embed_query/create_embedding_query_async), which differ because some
    embedding models (BGE, Cohere's input_type) are asymmetric: a query is
    embedded differently from the documents it's matched against.
    """

    def embed(self, text: str) -> List[float]:
        """Synchronous single-document embedding (indexing side)."""
        ...

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Synchronous batch document embedding (indexing side)."""
        ...

    def create_embedding(self, text: str) -> List[float]:
        """Synchronous single-text embedding. Alias of embed()."""
        ...

    async def create_embedding_async(self, text: str) -> List[float]:
        """Asynchronous single-document embedding (non-blocking)."""
        ...

    async def create_embedding_batch_async(self, texts: List[str]) -> List[List[float]]:
        """Asynchronous batch document embedding (non-blocking)."""
        ...

    def embed_query(self, query: str) -> List[float]:
        """Synchronous query embedding (retrieval side — may differ from embed())."""
        ...

    async def create_embedding_query_async(self, query: str) -> List[float]:
        """Asynchronous query embedding (non-blocking)."""
        ...


def create_ai_client() -> "AIClientProtocol":
    """
    Constructs the primary completion client — a BedrockClient configured
    from settings.BEDROCK_MODEL/AWS_REGION. Every call site that builds its
    own AI client (Celery tasks and other standalone/non-FastAPI usage)
    should call this instead of instantiating BedrockClient directly, so a
    model change stays one .env line, not a code change across every call
    site (see app/core/config.py::BEDROCK_MODEL for why Bedrock is the only
    provider).
    """
    from app.ai.bedrock_client import BedrockClient
    from app.core.config import settings

    return BedrockClient(model=settings.BEDROCK_MODEL, aws_region=settings.AWS_REGION)


def create_embedding_client() -> "EmbeddingClientProtocol":
    """
    Constructs the primary embedding client per settings.EMBEDDING_PROVIDER.
    Every call site should call this instead of instantiating
    LocalEmbeddingClient/BedrockEmbeddingClient directly, so switching
    provider — or switching Bedrock model (Cohere → Titan fallback) — stays
    a .env change, not a code change across every call site.

    "local" and "bedrock" produce vectors of different dimensionality
    (384 vs 1024) — switching EMBEDDING_PROVIDER at runtime without also
    re-running the matching Alembic migration and reindexing every run
    will fail at the pgvector column level (see app/core/config.py::
    EMBEDDING_DIMENSIONS and migration 024).
    """
    from app.core.config import settings

    if settings.EMBEDDING_PROVIDER == "local":
        from app.rag.embeddings.client import LocalEmbeddingClient
        return LocalEmbeddingClient()

    from app.rag.embeddings.bedrock_client import BedrockEmbeddingClient
    return BedrockEmbeddingClient(model=settings.BEDROCK_EMBEDDING_MODEL, aws_region=settings.AWS_REGION)
