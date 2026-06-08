"""
Query parameter profiling and fingerprinting.

Extracts and classifies query parameters observed across multiple HAR entries
for the same endpoint. Prevents false deduplication of semantically distinct
endpoints that share a path but differ only in query params
(e.g. GET /reports?type=monthly ≠ GET /reports?type=annual).

param_type classification:
  constant : same value in every observed call → hard-code in fingerprint
  variable : different values across calls → replace with {param_name}
  flag     : only boolean-like values (true/false, 0/1, active/inactive)
             → treated as variable (consumer must pass it)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Literal

from app.ingestion.models import TrafficEntry

_BOOLEAN_VALUES: frozenset[str] = frozenset({
    "true", "false", "1", "0", "yes", "no",
    "active", "inactive", "on", "off",
})


@dataclass
class QueryParamProfile:
    name: str
    param_type: Literal["constant", "variable", "flag"]
    observed_values: List[str] = field(default_factory=list)


def classify_query_params(
    all_calls: List[TrafficEntry],
    endpoint_key: str,
) -> Dict[str, QueryParamProfile]:
    """
    Classify each query parameter seen across all calls for an endpoint.

    constant → same value always (e.g. format=json)
    flag     → only boolean-like values (e.g. active=true|false)
    variable → multiple distinct non-boolean values (e.g. type=monthly|annual)
    """
    param_values: Dict[str, List[str]] = {}

    for entry in all_calls:
        for name, value in entry.query_params.items():
            param_values.setdefault(name, []).append(value)

    profiles: Dict[str, QueryParamProfile] = {}
    for name, values in param_values.items():
        # Preserve insertion order, deduplicate
        seen: dict[str, None] = {}
        for v in values:
            seen[v] = None
        unique_values = list(seen.keys())
        lower_values = {v.lower() for v in unique_values}

        if lower_values.issubset(_BOOLEAN_VALUES):
            param_type: Literal["constant", "variable", "flag"] = "flag"
        elif len(unique_values) == 1:
            param_type = "constant"
        else:
            param_type = "variable"

        profiles[name] = QueryParamProfile(
            name=name,
            param_type=param_type,
            observed_values=unique_values,
        )

    return profiles


def build_endpoint_fingerprint(
    method: str,
    path: str,
    query_params: Dict[str, QueryParamProfile],
) -> str:
    """
    Build a canonical endpoint fingerprint including variable/flag query params.

    Examples:
        "GET /reports?type={type}"
        "GET /employees?status={status}&page={page}"
        "GET /users?active=true"           (constant — hard-coded)
        "GET /data"                         (no query params)
    """
    if not query_params:
        return f"{method} {path}"

    parts: List[str] = []
    for name, profile in sorted(query_params.items()):
        if profile.param_type == "constant":
            parts.append(f"{name}={profile.observed_values[0]}")
        else:
            parts.append(f"{name}={{{name}}}")

    query_string = "&".join(parts)
    return f"{method} {path}?{query_string}"
