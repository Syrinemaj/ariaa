from typing import Optional

from app.ai.structured_outputs import ENDPOINT_UNDERSTANDING_SCHEMA
from app.models.endpoint import Endpoint


SYSTEM_PROMPT = """
You are an API documentation and business understanding engine.

Your task:
- understand the endpoint business meaning
- infer business domain
- infer business action
- create a short summary
- create a precise description
- propose useful tags
- return strict JSON only

Do not invent endpoints.
Use only the provided endpoint data.
"""


def enrich_endpoint_with_ai(endpoint: Endpoint, client=None) -> dict:
    """
    Enrich an endpoint with AI-generated metadata.

    client — an AIClientProtocol instance (GroqClient or AzureOpenAIClient).
    Falls back to GroqClient() if not provided (Celery / standalone usage).
    """
    if client is None:
        from app.ai.groq_client import GroqClient
        client = GroqClient()

    schema = endpoint.schema

    payload = {
        "method": endpoint.method,
        "path": endpoint.path,
        "canonical_key": endpoint.canonical_key,
        "business_domain": endpoint.business_domain,
        "business_action": endpoint.business_action,
        "request_schema": schema.request_schema if schema else None,
        "response_schema": schema.response_schema if schema else None,
        "auth_type": schema.auth_type if schema else None,
        "metadata": endpoint.metadata_json,
    }

    return client.structured_chat(
        system_prompt=SYSTEM_PROMPT,
        user_payload=payload,
        json_schema=ENDPOINT_UNDERSTANDING_SCHEMA,
        task_name="endpoint_understanding",
    )
