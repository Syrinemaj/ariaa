from typing import Dict, List

from app.normalization.models import NormalizedEndpoint
from app.schema_inference.auth_inference import infer_auth_from_headers
from app.schema_inference.models import EndpointSchemaResult
from app.schema_inference.request_schema import infer_request_schema
from app.schema_inference.response_schema import infer_response_schema
from app.schema_inference.schema_merger import merge_schemas


def infer_schema_for_endpoint(endpoint: NormalizedEndpoint) -> EndpointSchemaResult:
    request_schema = infer_request_schema(endpoint.request_body)
    response_schema = infer_response_schema(endpoint.response_body)

    auth = infer_auth_from_headers(
        request_headers=endpoint.metadata.get("request_headers", {}),
        response_headers=endpoint.metadata.get("response_headers", {}),
    )

    status_codes = [endpoint.status] if endpoint.status is not None else []

    return EndpointSchemaResult(
        method=endpoint.method,
        path=endpoint.normalized_path,
        canonical_key=endpoint.canonical_key,
        request_schema=request_schema,
        response_schema=response_schema,
        status_codes=status_codes,
        auth=auth,
        examples_count=endpoint.source_count,
        metadata={
            "original_path": endpoint.original_path,
            "phase2_score": endpoint.metadata.get("phase2_score"),
            "business_domain": endpoint.metadata.get("business_domain"),
            "business_action": endpoint.metadata.get("business_action"),
        },
    )


def infer_schemas_for_endpoints(endpoints: List[NormalizedEndpoint]) -> List[EndpointSchemaResult]:
    grouped: Dict[str, EndpointSchemaResult] = {}

    for endpoint in endpoints:
        result = infer_schema_for_endpoint(endpoint)
        key = result.canonical_key

        if key not in grouped:
            grouped[key] = result
            continue

        existing = grouped[key]
        existing.request_schema = merge_schemas(existing.request_schema, result.request_schema)
        existing.response_schema = merge_schemas(existing.response_schema, result.response_schema)
        existing.status_codes = sorted(set(existing.status_codes + result.status_codes))
        existing.examples_count += result.examples_count

    return list(grouped.values())
