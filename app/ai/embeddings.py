from app.models.endpoint import Endpoint


def build_endpoint_embedding_text(endpoint: Endpoint) -> str:
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
