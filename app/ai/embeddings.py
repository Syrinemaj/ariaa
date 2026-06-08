from typing import List

from app.models.endpoint import Endpoint


def build_endpoint_embedding_text(endpoint: Endpoint) -> str:
    """Build the text string that is embedded for an endpoint."""
    schema = endpoint.schema

    request_schema = schema.request_schema if schema else None
    response_schema = schema.response_schema if schema else None
    auth_type = schema.auth_type if schema else None

    parts = [
        f"HTTP method: {endpoint.method}",
        f"Path: {endpoint.path}",
        f"Canonical key: {endpoint.canonical_key}",
        f"Business domain: {endpoint.business_domain or 'unknown'}",
        f"Business action: {endpoint.business_action or 'unknown'}",
        f"Source count: {endpoint.source_count}",
        f"Authentication: {auth_type or 'unknown'}",
        f"Request schema: {request_schema or {}}",
        f"Response schema: {response_schema or {}}",
        f"Metadata: {endpoint.metadata_json or {}}",
    ]

    return "\n".join(parts)


def get_embedding(text: str) -> List[float]:
    """
    Embed a single text string using the local sentence-transformers model.

    Uses LocalEmbeddingClient with the class-level singleton — safe to call
    from both FastAPI routes and Celery workers.
    """
    from app.ai.local_embedding_client import LocalEmbeddingClient
    return LocalEmbeddingClient().create_embedding(text)
