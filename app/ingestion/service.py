from pathlib import Path
from typing import List

from app.ingestion.har_parser import parse_har_file
from app.ingestion.models import TrafficEntry
from app.ingestion.traffic_cleaner import clean_traffic
from app.ingestion.noise_scoring import score_entries


def process_har_file(
    file_path: str | Path,
    use_ai: bool = True,
    only_candidates: bool = True,
) -> List[TrafficEntry]:
    raw_entries = parse_har_file(file_path)
    cleaned_entries = clean_traffic(raw_entries)
    scored_entries = score_entries(cleaned_entries, use_ai=use_ai)

    if only_candidates:
        return [entry for entry in scored_entries if entry.is_api_candidate]

    return scored_entries
