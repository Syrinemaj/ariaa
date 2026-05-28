from typing import List

from app.rag.models import EndpointSearchResult


def build_rag_context(results: List[EndpointSearchResult]) -> str:
    blocks = []
    for index, result in enumerate(results, start=1):
        block = (
            f"Endpoint #{index}\n"
            f"Method: {result.method}\n"
            f"Path: {result.path}\n"
            f"Canonical key: {result.canonical_key}\n"
            f"Business domain: {result.business_domain or 'unknown'}\n"
            f"Business action: {result.business_action or 'unknown'}\n"
            f"Score: {result.score:.4f}\n"
            f"Details:\n{result.embedding_text}"
        )
        blocks.append(block)
    return "\n\n---\n\n".join(blocks)
