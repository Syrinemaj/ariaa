from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional

from app.ingestion.models import TrafficEntry
from app.ingestion.heuristic_filter import compute_heuristic_score
from app.ingestion.payload_classifier import compute_payload_score
from app.ingestion.semantic_filter import semantic_filter_with_azure


LOW_THRESHOLD = 0.30
HIGH_THRESHOLD = 0.70

# Ambiguous entries each cost one network-bound AI call (~2-10s); run them
# concurrently instead of one at a time — a HAR with hundreds of entries was
# otherwise spending most of process_har_file()'s wall time waiting on
# calls that don't touch shared state (each gets its own TrafficEntry).
_AI_CONCURRENCY = 8


def score_entry(
    entry: TrafficEntry,
    use_ai: bool = True,
    client=None,  # AIClientProtocol (create_ai_client()) shared across all entries in the batch
) -> TrafficEntry:
    heuristic_score = compute_heuristic_score(entry)
    payload_score = compute_payload_score(entry)

    entry.heuristic_score = heuristic_score
    entry.payload_score = payload_score

    combined_score = min(heuristic_score + payload_score, 1.0)
    entry.relevance_score = combined_score

    if combined_score >= HIGH_THRESHOLD:
        entry.is_api_candidate = True
        entry.is_ambiguous = False
        entry.decision = "kept_by_rules"
        entry.reason = "high_confidence_rules"
        return entry

    if combined_score <= LOW_THRESHOLD:
        entry.is_api_candidate = False
        entry.is_ambiguous = False
        entry.decision = "rejected_by_rules"
        entry.reason = "low_confidence_rules"
        return entry

    entry.is_ambiguous = True
    entry.decision = "ambiguous"

    if use_ai and client is not None:
        return semantic_filter_with_azure(entry, client=client)

    # No client available and score is ambiguous: apply conservative rejection.
    entry.is_api_candidate = False
    entry.decision = "rejected_no_client"
    entry.reason = "ambiguous_no_ai_client"
    return entry


def score_entries(
    entries: List[TrafficEntry],
    use_ai: bool = True,
) -> List[TrafficEntry]:
    """
    Score all entries using a single shared AI client instance.
    One client is created for the whole batch instead of one per ambiguous
    entry, avoiding redundant SSL handshakes and connection pools.
    """
    client: Optional[object] = None
    if use_ai:
        try:
            from app.ai.base_client import create_ai_client
            client = create_ai_client()
        except Exception:
            client = None

    if len(entries) <= 1:
        return [score_entry(entry, use_ai=use_ai, client=client) for entry in entries]

    with ThreadPoolExecutor(max_workers=_AI_CONCURRENCY) as pool:
        return list(pool.map(
            lambda entry: score_entry(entry, use_ai=use_ai, client=client),
            entries,
        ))
