from typing import Dict, List, Optional, Set, Tuple

from app.ingestion.models import TrafficEntry
from app.normalization.canonicalizer import build_canonical_key
from app.normalization.deduplication import deduplicate_endpoints
from app.normalization.dynamic_segment_detector import (
    detect_dynamic_positions,
    is_position_dynamic_for_entry,
)
from app.normalization.group_normalizer import build_group_hints
from app.normalization.models import NormalizedEndpoint
from app.normalization.url_normalizer import normalize_path


def _raw_segments(path: str) -> List[str]:
    return [s for s in path.split("/") if s]


def normalize_entry(
    entry: TrafficEntry,
    use_ai: bool = True,
    observed_dynamic_positions: Optional[Set[int]] = None,
    group_hint: Optional[Dict[int, dict]] = None,
) -> NormalizedEndpoint:
    normalized_path, parameters = normalize_path(
        method=entry.method,
        path_or_url=entry.path,
        request_body=entry.request_body,
        response_body=entry.response_body,
        use_ai=use_ai,
        observed_dynamic_positions=observed_dynamic_positions,
        group_hint=group_hint,
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
    # Computed once across the whole batch: an ID format regex doesn't
    # recognize (e.g. "emp_1", "emp_79d9baac") still gets templated if the
    # same position varies across other requests of the same shape in this
    # run. See dynamic_segment_detector.py for why this can't be done
    # per-entry in isolation.
    all_segments = [_raw_segments(entry.path) for entry in entries]
    dynamic_by_shape = detect_dynamic_positions([
        (entry.method, segs) for entry, segs in zip(entries, all_segments)
    ])

    # ARIA-NORM-FIX: dynamic_by_shape above is coarse — shared by every path
    # of a given (method, segment_count), regardless of which specific
    # paths actually proved a position variable. Applied blindly, a
    # position legitimate for one endpoint family (e.g. /webhooks/{hex})
    # leaks onto an unrelated family that merely has the same segment count
    # (e.g. /hr/employees vs /hr/departments — neither ID-shaped). Found via
    # a large-scale stress test mixing many families in one batch; the
    # golden dataset's isolated per-case calls never exposed it. Re-validate
    # per entry: keep a candidate position only if THIS entry has an actual
    # sibling (matches at every other position) with an ID-shaped value on
    # both sides at that position — see is_position_dynamic_for_entry().
    same_shape_segments: Dict[Tuple[str, int], List[List[str]]] = {}
    for entry, segs in zip(entries, all_segments):
        same_shape_segments.setdefault((entry.method.upper(), len(segs)), []).append(segs)

    validated_positions: List[Set[int]] = [
        {
            pos for pos in dynamic_by_shape.get((entry.method.upper(), len(segs)), set())
            if is_position_dynamic_for_entry(
                segs, pos, same_shape_segments[(entry.method.upper(), len(segs))],
            )
        }
        for entry, segs in zip(entries, all_segments)
    ]

    # One LLM call per endpoint group (all sibling URLs compared together)
    # instead of one call per isolated ambiguous segment — see
    # group_normalizer.py for why this catches non-standard ID formats the
    # per-segment path misses. Passed the same per-entry validated
    # positions (not the coarse dict) — group_normalizer.py had the exact
    # same propagation vulnerability via its own skeleton-masking step.
    group_hints = (
        build_group_hints(
            [(entry.method, entry.path) for entry in entries],
            validated_positions,
        )
        if use_ai
        else [None] * len(entries)
    )

    normalized = [
        normalize_entry(
            entry,
            use_ai=use_ai,
            observed_dynamic_positions=validated_positions[i],
            group_hint=group_hints[i],
        )
        for i, entry in enumerate(entries)
    ]

    if deduplicate:
        return deduplicate_endpoints(normalized)

    return normalized
