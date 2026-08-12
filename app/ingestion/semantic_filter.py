import logging
from typing import Dict, Any, Optional

from app.ingestion.models import TrafficEntry

logger = logging.getLogger(__name__)


def _build_ai_payload(entry: TrafficEntry) -> Dict[str, Any]:
    return {
        "method": entry.method,
        "url": entry.url,
        "path": entry.path,
        "status": entry.status,
        "mime_type": entry.mime_type,
        "request_headers": {
            key: value
            for key, value in entry.request_headers.items()
            if key in {"content-type", "accept"}
        },
        "response_headers": {
            key: value
            for key, value in entry.response_headers.items()
            if key in {"content-type"}
        },
        "request_body": entry.request_body,
        "response_body": entry.response_body,
        "heuristic_score": entry.heuristic_score,
        "payload_score": entry.payload_score,
    }


def semantic_filter_with_azure(
    entry: TrafficEntry,
    client,  # AIClientProtocol (create_ai_client()) — typed as Any to avoid circular import
) -> TrafficEntry:
    try:
        ai_payload = _build_ai_payload(entry)
        result = client.classify_api_call(ai_payload)

        # classify_api_call returns a ClassificationResponse Pydantic object
        confidence = result.confidence
        should_keep = result.should_keep

        entry.ai_score = confidence
        entry.business_domain = result.business_domain
        entry.business_action = result.business_action
        entry.reason = result.reason

        if should_keep:
            entry.is_api_candidate = True
            entry.decision = "kept_by_ai"
            entry.relevance_score = max(entry.relevance_score, confidence)
        else:
            entry.is_api_candidate = False
            entry.decision = "rejected_by_ai"
            entry.relevance_score = confidence

    except Exception as e:
        # AI unavailable: reject ambiguous entries rather than silently accepting
        # them, to avoid flooding the registry with noise.
        logger.warning(
            "semantic_filter.ai_unavailable — rejecting ambiguous entry: %s %s | error: %s",
            entry.method, entry.path, e,
        )
        _increment_fallback_counter()
        entry.is_api_candidate = False
        entry.decision = "rejected_by_fallback"
        entry.reason = "ai_unavailable"

    return entry


def _increment_fallback_counter() -> None:
    try:
        from app.observability.metrics import aria_semantic_filter_fallback_total
        aria_semantic_filter_fallback_total.inc()
    except Exception:
        pass
