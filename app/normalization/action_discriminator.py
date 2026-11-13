"""
App-agnostic detection of "multiplexed" endpoints — one URL/method that
carries several distinct business actions, selected by a body field, rather
than by the path (REST-style APIs put the action in the URL; RPC-style
enterprise backends often don't).

canonicalizer.py used to special-case this with a hardcoded field-name list
(dataSectionName/dsName/dataStructureName) discovered on one SopraHR HAR.
That only ever works for that one backend. This module instead detects the
pattern structurally, from the actual traffic of the current run, so it
generalizes to any app that reuses one URL for several operations — SopraHR,
a "generic RPC" gateway keyed by an "action"/"operation"/"eventType" field,
or anything else with the same shape:

  A field is a real action discriminator only if grouping bodies by its
  value also groups them by BODY SHAPE (which other fields are present,
  nested structure) — not merely by value. A "status" field that takes a
  handful of values inside an otherwise identical body is not multiplexing
  anything; it's just data. dataSectionName is, because "AG" bodies and "AD"
  bodies carry different field sets.

This needs the full set of request bodies observed for one (method,
normalized_path) in the current ingestion run — a single isolated body
carries no such signal, exactly like dynamic_segment_detector.py and
group_normalizer.py need siblings, not one example, to tell a real ID/group
from a coincidence. Call detect_action_discriminator_field() once per
(method, normalized_path) group; batching across the whole run happens in
normalization/service.py.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

_MIN_GROUP_SIZE = 2          # need at least 2 bodies to compare anything —
                             # same floor group_normalizer.py and
                             # dynamic_segment_detector.py use for their own
                             # cross-request comparisons. Real captures from
                             # a manual test session routinely have only 1-2
                             # examples per multiplexed action variant (a
                             # tester submits one leave request, changes one
                             # address); requiring 3+ would mean this never
                             # fires on exactly the traffic it exists for.
_MAX_BODIES = 30             # cap pairwise-comparison cost on huge groups
# Deep enough to see INTO the payload that actually distinguishes actions,
# not just down to the selector field. Real enterprise RPC bodies nest the
# selector and its associated data several levels down — observed directly
# on real SopraHR traffic: body.dossiers[].sections[].dataSectionName (the
# selector) sits at depth 4, but the fields that make an "AG" congé row
# structurally different from an "AD" address row —
# body.dossiers[].sections[].rows[].valueMap.{field} — only appear at depth
# 7. canonicalizer._find_field_anywhere's depth=4 is a different, shallower
# job (finding one named field's value near the top) and is left alone;
# this constant is for comparing whole-body SHAPE, which needs to reach the
# actual varying payload, not just the selector sitting next to it. Cost is
# still bounded by _MAX_BODIES, not depth, so going deeper here is cheap.
_MAX_DEPTH = 10
_MIN_PRESENCE_RATIO = 0.5     # field must show up in at least half the bodies
# Cardinality gate: an absolute bound on the field's vocabulary size, not a
# ratio of the sample seen so far. A ratio (distinct/n) breaks at small n —
# with 2 examples, a real action code (2 distinct values) and a per-request
# ID (2 distinct values) look identical by that measure. A small business
# vocabulary (action codes, section names, operation types) rarely exceeds
# a dozen values regardless of how many requests are sampled; a per-request
# identifier or free-text field will blow past this bound as more examples
# accumulate. The structural shape-correlation check below (not this gate)
# is what actually rejects IDs/free text at low n.
_MIN_CARDINALITY = 2
_MAX_CARDINALITY = 12
_MIN_SCORE = 0.25             # min (intra - inter) shape-similarity gap
_MIN_INTRA_SIMILARITY = 0.4   # same-value bodies must actually look alike


def _collect_scalar_field_names(body: Any, depth: int = 0, out: Optional[Set[str]] = None) -> Set[str]:
    """All field names holding a non-empty string leaf, anywhere in the tree
    (up to _MAX_DEPTH) — the universe of discriminator candidates."""
    if out is None:
        out = set()
    if depth > _MAX_DEPTH or body is None:
        return out
    if isinstance(body, dict):
        for key, value in body.items():
            if isinstance(value, str) and value.strip():
                out.add(key)
            else:
                _collect_scalar_field_names(value, depth + 1, out)
    elif isinstance(body, list):
        for item in body[:5]:
            _collect_scalar_field_names(item, depth + 1, out)
    return out


def _find_field_value(body: Any, field: str, depth: int = 0) -> Optional[str]:
    """Same matching rule as canonicalizer._find_field_anywhere, duplicated
    at the value level (candidate collection above needs its own traversal;
    keeping both self-contained avoids a two-way import between this module
    and canonicalizer.py)."""
    if depth > _MAX_DEPTH or body is None:
        return None
    if isinstance(body, dict):
        value = body.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
        for v in body.values():
            found = _find_field_value(v, field, depth + 1)
            if found:
                return found
        return None
    if isinstance(body, list):
        for item in body[:5]:
            found = _find_field_value(item, field, depth + 1)
            if found:
                return found
    return None


def _flatten_key_paths(body: Any, depth: int = 0, prefix: str = "", out: Optional[Set[str]] = None) -> Set[str]:
    """Dotted key paths present in the tree (up to _MAX_DEPTH) — the 'shape
    signature' used to compare bodies structurally rather than by value."""
    if out is None:
        out = set()
    if depth > _MAX_DEPTH or body is None:
        return out
    if isinstance(body, dict):
        for key, value in body.items():
            path = f"{prefix}.{key}" if prefix else key
            out.add(path)
            _flatten_key_paths(value, depth + 1, path, out)
    elif isinstance(body, list):
        for item in body[:5]:
            _flatten_key_paths(item, depth + 1, prefix, out)
    return out


def _jaccard(a: Set[str], b: Set[str]) -> float:
    if not a and not b:
        return 1.0
    union = a | b
    if not union:
        return 1.0
    return len(a & b) / len(union)


def _mean_pairwise_jaccard(signatures: List[Set[str]]) -> float:
    """Mean Jaccard similarity over all pairs; 1.0 for a single signature
    (nothing to disagree with)."""
    n = len(signatures)
    if n < 2:
        return 1.0
    total, count = 0.0, 0
    for i in range(n):
        for j in range(i + 1, n):
            total += _jaccard(signatures[i], signatures[j])
            count += 1
    return total / count if count else 1.0


def detect_action_discriminator_field(bodies: List[Any]) -> Optional[str]:
    """
    bodies: every request_body observed in this run for one (method,
    normalized_path) group.

    Returns the field name that best explains the group as several distinct
    multiplexed actions, or None if the group looks like one ordinary
    operation (uniform shape, or too few examples to tell).
    """
    dict_bodies = [b for b in bodies if isinstance(b, dict) and b][:_MAX_BODIES]
    if len(dict_bodies) < _MIN_GROUP_SIZE:
        return None

    shape_signatures = [_flatten_key_paths(b) for b in dict_bodies]

    # Uniform shape across the whole group: nothing to discriminate — every
    # body already looks like the same operation, just different data.
    if _mean_pairwise_jaccard(shape_signatures) > 0.9:
        return None

    candidates: Set[str] = set()
    for body in dict_bodies:
        candidates |= _collect_scalar_field_names(body)

    n = len(dict_bodies)
    best_field: Optional[str] = None
    best_score = _MIN_SCORE

    for field in candidates:
        values = [_find_field_value(body, field) for body in dict_bodies]
        present = [v for v in values if v is not None]
        if len(present) / n < _MIN_PRESENCE_RATIO:
            continue

        distinct = set(present)
        if not (_MIN_CARDINALITY <= len(distinct) <= _MAX_CARDINALITY):
            continue

        groups: Dict[str, List[Set[str]]] = {}
        for value, signature in zip(values, shape_signatures):
            if value is None:
                continue
            # Exclude the candidate field's own key from the signature so a
            # field can't "explain" the shape difference merely by its own
            # presence/absence — the OTHER fields must actually differ.
            groups.setdefault(value, []).append(
                {k for k in signature if k.split(".")[-1] != field}
            )

        if len(groups) < 2:
            continue

        intra_scores = [_mean_pairwise_jaccard(sigs) for sigs in groups.values() if len(sigs) >= 1]
        intra = sum(intra_scores) / len(intra_scores) if intra_scores else 0.0
        if intra < _MIN_INTRA_SIMILARITY:
            continue

        representatives = [sigs[0] for sigs in groups.values()]
        inter = _mean_pairwise_jaccard(representatives)

        score = intra - inter
        if score > best_score or (score == best_score and best_field is not None and field < best_field):
            best_score = score
            best_field = field

    return best_field
