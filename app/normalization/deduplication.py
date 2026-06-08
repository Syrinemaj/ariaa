from typing import Any, Dict, List, Optional, Tuple

from app.normalization.models import NormalizedEndpoint


_SUCCESS_STATUSES = {200, 201, 202, 203}


def _count_useful_fields(body: Any, depth: int = 0) -> int:
    """Recursively count non-null leaf values. Depth-capped at 5."""
    if depth > 5 or body is None:
        return 0
    if isinstance(body, dict):
        total = 0
        for v in body.values():
            if v is not None:
                total += 1 + _count_useful_fields(v, depth + 1)
        return total
    if isinstance(body, list) and body:
        return _count_useful_fields(body[0], depth + 1)
    return 1  # scalar non-null value


def _body_score(body: Any, status: Optional[int], prefer_success: bool) -> int:
    """
    Score a body candidate — higher is better.

    Rules:
      - None or non-dict/list           → -1 (discard)
      - empty dict {}                   →  0 (valid but useless)
      - otherwise: count of non-null fields, with a +100 bonus for 2xx status
        when prefer_success=True (used for response bodies).
    """
    if body is None or not isinstance(body, (dict, list)):
        return -1
    if isinstance(body, dict) and not body:
        return 0

    score = _count_useful_fields(body)

    if prefer_success and status in _SUCCESS_STATUSES:
        score += 100

    return score


def _best_body(
    candidates: List[Tuple[Any, Optional[int]]],
    prefer_success: bool,
) -> Any:
    """Return the body with the highest score among (body, status) candidates."""
    best: Any = None
    best_score = -2  # below the -1 floor so None wins over no candidates
    for body, status in candidates:
        s = _body_score(body, status, prefer_success)
        if s > best_score:
            best_score = s
            best = body
    return best


def deduplicate_endpoints(
    endpoints: List[NormalizedEndpoint],
) -> List[NormalizedEndpoint]:
    """
    Merge endpoints with the same canonical_key (method + normalized_path).

    Body selection strategy:
      - request_body : richest body across all examples (most non-null fields).
      - response_body: richest body from a 2xx response; falls back to any
                       non-null body if no 2xx example exists.
    """
    grouped: Dict[str, NormalizedEndpoint] = {}
    req_candidates: Dict[str, List[Tuple[Any, Optional[int]]]] = {}
    res_candidates: Dict[str, List[Tuple[Any, Optional[int]]]] = {}

    for endpoint in endpoints:
        key = endpoint.canonical_key

        if key not in grouped:
            grouped[key] = endpoint.model_copy(deep=True)
            grouped[key].metadata.setdefault("examples", [])
            req_candidates[key] = []
            res_candidates[key] = []
        else:
            grouped[key].source_count += 1

        grouped[key].metadata["examples"].append({
            "original_url": endpoint.original_url,
            "original_path": endpoint.original_path,
            "status": endpoint.status,
        })

        req_candidates[key].append((endpoint.request_body, endpoint.status))
        res_candidates[key].append((endpoint.response_body, endpoint.status))

    for key, ep in grouped.items():
        ep.request_body = _best_body(req_candidates[key], prefer_success=False)
        ep.response_body = _best_body(res_candidates[key], prefer_success=True)

    return list(grouped.values())
