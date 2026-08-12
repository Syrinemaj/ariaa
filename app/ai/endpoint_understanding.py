from typing import Optional

from app.ai.structured_outputs import ENDPOINT_UNDERSTANDING_SCHEMA
from app.models.endpoint import Endpoint


SYSTEM_PROMPT = """You are an API documentation and business understanding engine, enriching
an endpoint AFTER it has already been classified as business-relevant.

business_domain and business_action in the input MAY already be populated
by an earlier classification pass — refine them only if the endpoint's
actual schema/path clearly suggests a more specific or different value;
otherwise keep them as given. Do not silently overwrite a reasonable
existing value just to produce a different-looking answer.

Your task, from the endpoint data provided (method, path, canonical_key,
request/response JSON schema, auth_type):
- business_domain: confirm or refine (see above)
- business_action: confirm or refine (see above)
- summary: ONE sentence, plain language, for a non-technical reader
- description: 2-3 sentences, technical — mention the resource, key request/
  response fields, and any notable constraint (auth required, etc.)
- tags: 3-5 lowercase single-word or snake_case tags (resource names or
  capabilities, not generic words like "api" or "endpoint")
- confidence: 0.8-1.0 when the schema clearly describes a well-known CRUD
  operation, 0.5-0.8 when domain/action are plausible but underspecified,
  <0.5 when the schema is too sparse to say much beyond the HTTP method

Do not invent endpoints, fields, or schema content not present in the input.
Return strict JSON only.
"""


def enrich_endpoint_with_ai(endpoint: Endpoint, client=None) -> dict:
    """
    Enrich an endpoint with AI-generated metadata.

    client — an AIClientProtocol instance (BedrockClient, GroqClient or
    AzureOpenAIClient). Falls back to create_ai_client() if not provided
    (Celery / standalone usage).
    """
    if client is None:
        from app.ai.base_client import create_ai_client
        client = create_ai_client()

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
