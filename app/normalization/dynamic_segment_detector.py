"""
Cross-request statistical detection of dynamic path segments.

Regex-based detection (parameter_detector.py) only recognizes ID formats
anticipated in advance (UUID, numeric, Stripe-style, prefixed business IDs,
etc.) — any convention outside that list (e.g. "emp_1", "emp_79d9baac") is
silently kept as a static literal, fragmenting what should be one endpoint
into one per observed ID value.

This module catches those by comparing paths observed within the SAME
ingestion run: if a segment position varies between two otherwise-identical
paths (same method, same segment count, every other position equal), that
position is almost certainly a resource identifier — regardless of what it
looks like.

Known trade-off: two genuinely distinct static siblings at the same position
(e.g. /reports/monthly vs /reports/annual) would also get flagged if nothing
else in the run disambiguates them. This mirrors the rest of the
normalization pipeline (confidence-scored, human-reviewable via the
registry) rather than trying to be a perfect classifier — false positives
here are visible and correctable, silently-missed real IDs are not.

One case is excluded outright rather than left to that trade-off: a
candidate position directly after a known version/environment segment (v1,
v2, latest, staging...). /api/v1/employees, /api/v1/products, /api/v1/orders
etc. all differ at exactly one position with everything else constant —
textbook match for the heuristic above — but that position is enumerating
entirely different top-level resources, not IDs of the same resource. This
was caught empirically: an early version of this module collapsed exactly
that shape into a fabricated "/api/v1/{v1_id}" endpoint.
"""
from __future__ import annotations

from typing import Dict, List, Set, Tuple

from app.normalization.parameter_detector import _STATIC_SEGMENTS, detect_parameter_type

GroupKey = Tuple[str, int]  # (method, segment_count)


def detect_dynamic_positions(
    paths: List[Tuple[str, List[str]]],
) -> Dict[GroupKey, Set[int]]:
    """
    paths: list of (method, raw_segments) observed in one ingestion run.

    Returns, per (method, segment_count) group, the set of segment indices
    that vary across observed requests while every other position stays
    identical.

    Iterative fixed point: repeatedly compare all pairs of segment lists in
    a group; if two differ at exactly one not-yet-dynamic position, mark it
    dynamic. Repeating until no new positions are found lets multi-parameter
    paths (e.g. /employees/{id}/contracts/{contract_id}) resolve correctly
    even when no single pair of requests isolates both at once.
    """
    groups: Dict[GroupKey, List[List[str]]] = {}
    for method, segments in paths:
        if not segments:
            continue
        key = (method.upper(), len(segments))
        group = groups.setdefault(key, [])
        if segments not in group:  # skip exact duplicates, no new signal
            group.append(segments)

    result: Dict[GroupKey, Set[int]] = {}

    for key, segment_lists in groups.items():
        length = key[1]
        dynamic: Set[int] = set()

        if len(segment_lists) < 2:
            result[key] = dynamic
            continue

        changed = True
        while changed:
            changed = False
            for i in range(len(segment_lists)):
                for j in range(i + 1, len(segment_lists)):
                    a, b = segment_lists[i], segment_lists[j]
                    diff_positions = [
                        pos for pos in range(length)
                        if pos not in dynamic and a[pos] != b[pos]
                    ]
                    if len(diff_positions) != 1:
                        continue
                    pos = diff_positions[0]
                    if pos > 0 and a[pos - 1].lower() in _STATIC_SEGMENTS:
                        continue
                    # ARIA-NORM-FIX: positional variance alone is not enough —
                    # two structurally-unrelated endpoints that happen to
                    # share (method, segment_count) and differ at exactly one
                    # position (e.g. POST /api/v1/hr/employees vs
                    # POST /api/v1/hr/departments) would otherwise be
                    # collapsed into one fake templated endpoint. Require
                    # BOTH differing values to independently look ID-shaped
                    # (parameter_detector.detect_parameter_type) — a plain
                    # resource-name word never does, no matter how much it
                    # varies positionally. This also blocks the cascade bug
                    # where, once a real ID position is excluded from future
                    # diff-counts (see the fixed-point loop above), an
                    # adjacent literal action segment (e.g. "contract" vs
                    # "salary") could become the sole remaining difference
                    # and get wrongly templated too.
                    if detect_parameter_type(a[pos]) is None or detect_parameter_type(b[pos]) is None:
                        continue
                    dynamic.add(pos)
                    changed = True

        result[key] = dynamic

    return result


def is_position_dynamic_for_entry(
    segments: List[str],
    pos: int,
    same_shape_segments: List[List[str]],
) -> bool:
    """
    ARIA-NORM-FIX: detect_dynamic_positions() above returns a COARSE result
    keyed only by (method, segment_count) — shared across every path of
    that shape, regardless of which specific paths triggered it. That
    global sharing is itself a bug: a position legitimately dynamic for one
    endpoint family (e.g. /webhooks/{hex}, proven by real ID-shaped
    variance) gets blindly applied to an unrelated family that merely
    happens to share the same segment count (e.g. /hr/employees vs
    /hr/departments — 2 segments, same as /webhooks/{hex}, but neither
    "employees" nor "departments" is ID-shaped). Found via a large-scale
    stress test mixing many endpoint families in one batch — the golden
    dataset never caught it because each of its cases runs in an isolated
    normalize_entries() call, so no cross-family contamination was
    possible there.

    This is the per-entry gate callers (service.py, group_normalizer.py)
    must apply before trusting a candidate position from
    detect_dynamic_positions() for a SPECIFIC path: true only if that path
    has an actual sibling in `same_shape_segments` — one that matches it at
    every other position and differs, in an ID-shaped way on both sides, at
    `pos`.
    """
    for other in same_shape_segments:
        if other is segments or len(other) != len(segments):
            continue
        diffs = [i for i in range(len(segments)) if other[i] != segments[i]]
        if diffs == [pos] and detect_parameter_type(segments[pos]) is not None and detect_parameter_type(other[pos]) is not None:
            return True
    return False
