from typing import List

from app.ingestion.models import TrafficEntry
from app.normalization.canonicalizer import build_canonical_key
from app.normalization.deduplication import deduplicate_endpoints
from app.normalization.models import NormalizedEndpoint
from app.normalization.url_normalizer import normalize_path


def normalize_entry(
    entry: TrafficEntry,
    use_ai: bool = True,
) -> NormalizedEndpoint:
    normalized_path, parameters = normalize_path(
        method=entry.method,
        path_or_url=entry.path,
        request_body=entry.request_body,
        response_body=entry.response_body,
        use_ai=use_ai,
    )

    canonical_key = build_canonical_key(
        method=entry.method,
        normalized_path=normalized_path,
    )

    return NormalizedEndpoint(
        method=entry.method,
        original_url=entry.url,
        original_path=entry.path,
        normalized_path=normalized_path,
        path_parameters=parameters,
        canonical_key=canonical_key,
        status=entry.status,
        mime_type=entry.mime_type,
        request_body=entry.request_body,
        response_body=entry.response_body,
        metadata={
            "phase2_decision": entry.decision,
            "phase2_score": entry.relevance_score,
            "business_domain": entry.business_domain,
            "business_action": entry.business_action,
            "request_headers": entry.request_headers,
            "response_headers": entry.response_headers,
        },
    )


def normalize_entries(
    entries: List[TrafficEntry],
    use_ai: bool = True,
    deduplicate: bool = True,
) -> List[NormalizedEndpoint]:
    normalized = [normalize_entry(entry, use_ai=use_ai) for entry in entries]

    if deduplicate:
        return deduplicate_endpoints(normalized)

    return normalized
