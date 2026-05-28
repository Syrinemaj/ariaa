from app.ai.azure_openai_client import AzureOpenAIClient
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


def enrich_endpoint_with_ai(endpoint: Endpoint) -> dict:
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

    client = AzureOpenAIClient()
    return client.structured_chat(
        system_prompt=SYSTEM_PROMPT,
        user_payload=payload,
        json_schema=ENDPOINT_UNDERSTANDING_SCHEMA,
        task_name="endpoint_understanding",
    )
