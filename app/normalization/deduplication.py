from typing import Dict, List

from app.normalization.models import NormalizedEndpoint


def deduplicate_endpoints(
    endpoints: List[NormalizedEndpoint],
) -> List[NormalizedEndpoint]:
    grouped: Dict[str, NormalizedEndpoint] = {}

    for endpoint in endpoints:
        key = endpoint.canonical_key

        if key not in grouped:
            grouped[key] = endpoint
            grouped[key].metadata.setdefault("examples", [])
            grouped[key].metadata["examples"].append({
                "original_url": endpoint.original_url,
                "original_path": endpoint.original_path,
                "status": endpoint.status,
            })
            continue

        existing = grouped[key]
        existing.source_count += 1
        existing.metadata.setdefault("examples", [])
        existing.metadata["examples"].append({
            "original_url": endpoint.original_url,
            "original_path": endpoint.original_path,
            "status": endpoint.status,
        })

    return list(grouped.values())
