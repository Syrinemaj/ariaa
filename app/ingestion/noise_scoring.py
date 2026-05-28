from typing import List

from app.ingestion.models import TrafficEntry
from app.ingestion.heuristic_filter import compute_heuristic_score
from app.ingestion.payload_classifier import compute_payload_score
from app.ingestion.semantic_filter import semantic_filter_with_azure


LOW_THRESHOLD = 0.30
HIGH_THRESHOLD = 0.70


def score_entry(entry: TrafficEntry, use_ai: bool = True) -> TrafficEntry:
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

    if use_ai:
        return semantic_filter_with_azure(entry)

    return entry


def score_entries(entries: List[TrafficEntry], use_ai: bool = True) -> List[TrafficEntry]:
    return [score_entry(entry, use_ai=use_ai) for entry in entries]
