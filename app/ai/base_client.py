"""
AI client protocols — structural subtyping via typing.Protocol.

Two protocols are defined:
  AIClientProtocol     — completion methods. GroqClient is the primary
    provider (AI_PROVIDER=groq, the default); AzureOpenAIClient is a
    separate standalone provider (AI_PROVIDER=azure), not a fallback that
    GroqClient reaches for internally.
  EmbeddingClientProtocol — embedding methods (LocalEmbeddingClient only)

Both GroqClient and AzureOpenAIClient satisfy AIClientProtocol without
inheriting from it (duck typing / structural subtyping).
LocalEmbeddingClient satisfies EmbeddingClientProtocol.

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
    required schema fields even after a retry — see GroqClient.structured_chat.
    Callers should catch this and surface a clean error, not a raw KeyError."""


@runtime_checkable
class AIClientProtocol(Protocol):
    """
    Completion client — implemented by GroqClient and AzureOpenAIClient.
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
    Embedding client — implemented by LocalEmbeddingClient.
    Kept separate from AIClientProtocol because the providers are different:
    completions → Groq/Azure, embeddings → local sentence-transformers.
    """

    def create_embedding(self, text: str) -> List[float]:
        """Synchronous single-text embedding."""
        ...

    async def create_embedding_async(self, text: str) -> List[float]:
        """Asynchronous single-text embedding (non-blocking)."""
        ...
