"""
AI client protocols — structural subtyping via typing.Protocol.

Two protocols are defined:
  AIClientProtocol     — completion methods, implemented by BedrockClient
    (AI_PROVIDER=bedrock, the default), GroqClient (AI_PROVIDER=groq), and
    AzureOpenAIClient (AI_PROVIDER=azure) — three independent providers,
    none of them a fallback the others reach for internally. Pick one via
    create_ai_client() below rather than importing a concrete client.
  EmbeddingClientProtocol — embedding methods (LocalEmbeddingClient only)

BedrockClient, GroqClient and AzureOpenAIClient all satisfy AIClientProtocol
without inheriting from it (duck typing / structural subtyping).
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


def create_ai_client() -> "AIClientProtocol":
    """
    Constructs the primary completion client per settings.AI_PROVIDER —
    every call site that used to hardcode GroqClient() (Celery tasks and
    other standalone/non-FastAPI usage) should call this instead, so a
    provider change is one .env line, not a code change in ~10 files.

    Not to be confused with azure_openai_client.py's get_ai_client(request)
    — that one is the FastAPI dependency returning the already-constructed
    app.state.ai_client singleton; this one BUILDS a new client instance.
    """
    from app.core.config import settings

    if settings.AI_PROVIDER == "azure":
        from app.ai.azure_openai_client import AzureOpenAIClient
        return AzureOpenAIClient()
    if settings.AI_PROVIDER == "bedrock":
        from app.ai.bedrock_client import BedrockClient
        return BedrockClient(model=settings.BEDROCK_MODEL, aws_region=settings.AWS_REGION)
    from app.ai.groq_client import GroqClient
    return GroqClient()
