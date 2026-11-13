"""
BedrockEmbeddingClient — AWS Bedrock embedding models via boto3 invoke_model.

Primary model: Cohere Embed Multilingual v3 (cohere.embed-multilingual-v3),
chosen over Amazon Titan Text Embeddings V2 for cross-lingual (FR/EN)
retrieval quality — ARIA's endpoint corpus and user queries are frequently
French, and the prior model (BAAI/bge-small-en, see client.py) is
English-only, with French content only reaching the index when an LLM
summarization step happened to translate it. 1024 output dimensions
(see app/core/config.py::EMBEDDING_DIMENSIONS and migration 024).

Fallback: Amazon Titan Text Embeddings V2 (amazon.titan-embed-text-v2:0),
switched to via BEDROCK_EMBEDDING_MODEL alone — no code change — if Cohere
model access isn't enabled on the target AWS account/region. Also 1024 dims
by default, so no migration is needed to fall back.

Unlike chat completion (app/ai/bedrock_client.py, which uses the Converse
API exclusively), Bedrock embedding models are invoked via invoke_model —
Converse does not support embedding models. The two providers below use
different request/response JSON shapes, dispatched on the model id prefix:

Cohere (cohere.embed-multilingual-v3):
  request:  {"texts": [...], "input_type": "search_document"|"search_query"}
  response: {"embeddings": [[float, ...], ...]}
  Batches natively — one invoke_model call embeds every text in `texts`.
  input_type is Cohere's native equivalent of the hand-rolled BGE query
  instruction prefix in client.py — no bespoke prefix string needed here.

Amazon Titan Text Embeddings V2 (amazon.titan-embed-text-v2:0):
  request:  {"inputText": "...", "dimensions": 1024, "normalize": true}
  response: {"embedding": [float, ...]}
  One text per invoke_model call — batch methods loop client-side.
  Titan has no query/document asymmetry; embed() and embed_query() are
  identical for this model.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import List, Optional

import boto3

from app.core.config import settings

logger = logging.getLogger(__name__)


class BedrockEmbeddingClient:
    """Satisfies the same call-site interface as LocalEmbeddingClient
    (embed/embed_batch/create_embedding*/embed_query/create_embedding_query_async)
    so it is a drop-in replacement behind create_embedding_client()."""

    def __init__(self, model: Optional[str] = None, aws_region: Optional[str] = None) -> None:
        self.model = model or settings.BEDROCK_EMBEDDING_MODEL
        self._is_cohere = self.model.startswith("cohere.")
        self._client = boto3.client("bedrock-runtime", region_name=aws_region or settings.AWS_REGION)

    # ── Core invoke_model dispatch ───────────────────────────────────────────

    def _invoke_batch(self, texts: List[str], input_type: str) -> List[List[float]]:
        if self._is_cohere:
            body = json.dumps({"texts": texts, "input_type": input_type})
            response = self._client.invoke_model(
                modelId=self.model, body=body,
                accept="application/json", contentType="application/json",
            )
            payload = json.loads(response["body"].read())
            return payload["embeddings"]

        # Titan — no native batching, one invoke_model call per text.
        out: List[List[float]] = []
        for text in texts:
            body = json.dumps({
                "inputText": text,
                "dimensions": settings.EMBEDDING_DIMENSIONS,
                "normalize": True,
            })
            response = self._client.invoke_model(
                modelId=self.model, body=body,
                accept="application/json", contentType="application/json",
            )
            payload = json.loads(response["body"].read())
            out.append(payload["embedding"])
        return out

    # ── Document / indexing side (input_type=search_document) ───────────────

    def embed(self, text: str) -> List[float]:
        return self._invoke_batch([text], "search_document")[0]

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return self._invoke_batch(texts, "search_document")

    def create_embedding(self, text: str) -> List[float]:
        return self.embed(text)

    async def create_embedding_async(self, text: str) -> List[float]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.embed, text)

    async def create_embedding_batch_async(self, texts: List[str]) -> List[List[float]]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.embed_batch, texts)

    # ── Query / retrieval side (input_type=search_query) ─────────────────────

    def embed_query(self, query: str) -> List[float]:
        return self._invoke_batch([query], "search_query")[0]

    async def create_embedding_query_async(self, query: str) -> List[float]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.embed_query, query)
