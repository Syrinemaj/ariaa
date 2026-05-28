import logging
from typing import Dict, Any

from app.ai.azure_openai_client import AzureOpenAIClient
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


def semantic_filter_with_azure(entry: TrafficEntry) -> TrafficEntry:
    try:
        client = AzureOpenAIClient()
        ai_payload = _build_ai_payload(entry)
        result = client.classify_api_call(ai_payload)

        confidence = float(result.get("confidence", 0.0))
        should_keep = bool(result.get("should_keep", False))

        entry.ai_score = confidence
        entry.business_domain = result.get("business_domain")
        entry.business_action = result.get("business_action")
        entry.reason = result.get("reason")

        if should_keep:
            entry.is_api_candidate = True
            entry.decision = "kept_by_ai"
            entry.relevance_score = max(entry.relevance_score, confidence)
        else:
            entry.is_api_candidate = False
            entry.decision = "rejected_by_ai"
            entry.relevance_score = confidence

    except Exception as e:
        logger.warning("Azure OpenAI unavailable, keeping ambiguous entry: %s", e)
        entry.is_api_candidate = True
        entry.decision = "kept_by_fallback"
        entry.reason = "ai_unavailable"

    return entry
