"""
Workflow dependency detection — no LLM required.

Pass 1: a mutating step (POST/PUT/PATCH/DELETE) depends on the previous
  mutating step in the sequence — a positional guess, kept as a fallback for
  when no concrete data link is found (passes 2/3 below).

Pass 2: schema-based detection on the single deduplicated example body each
  step carries — if a POST/PUT step's response contains a field named "id"
  or ending in "_id", and a later step's path has a matching {param}
  placeholder (by NAME only), the later step depends on the creator step.

Pass 3 (real value correlation — needs raw_calls): passes 1-2 above never
  look at an actual captured value, only field/param NAMES on whatever single
  example deduplicate_endpoints() happened to keep — so e.g. POST /employees
  then PUT /employees/{id} link up "correctly" by accident of positional
  order, not because anyone checked the id POST actually returned is the
  same id the PUT's path used. Pass 3 walks the real pre-dedup per-call list
  (raw_calls — one entry per original HAR call, real request/response
  bodies, true capture order) and only links two steps when an identifier
  VALUE produced in one call's response is later consumed by name in either
  a path parameter or a request-body field of a DIFFERENT call. This also
  catches a dependency passes 1-2 structurally cannot: a foreign key carried
  in a request BODY rather than the URL (e.g. POST /requests with
  {"employee_id": 2} depending on whichever call produced employee id 2),
  since pass 2 only ever looks at path params.

Example (pass 3):
  POST /employees → response: {"id": 6, "full_name": "Julien Mercier"}
  PUT  /employees/{employee_id}, this specific call's path param = "6"
  → PUT step gains depends_on = ["POST /employees canonical_key"], because
    6 == 6 was actually checked — not just that both mention "id".
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from app.workflows.models import WorkflowStep

logger = logging.getLogger(__name__)

_ID_FIELD_SUFFIXES = ("_id", "Id")


def _looks_like_id_field(field_name: str) -> bool:
    return field_name == "id" or field_name.endswith(_ID_FIELD_SUFFIXES)


def _is_plausible_id_value(value: Any) -> bool:
    """Guard against matching on trivial/common values (True, 0, "", short
    non-numeric flags) that would otherwise produce false-positive
    dependency edges. A path parameter's raw_value is always a string even
    for a single-digit numeric id ("1") — only requiring length >= 2 for
    non-numeric strings keeps that legitimate, common case from being
    silently rejected, while still screening out meaningless 1-char tokens
    like "x" or "-"."""
    if isinstance(value, bool) or value is None:
        return False
    if isinstance(value, int):
        return value > 0
    if isinstance(value, str):
        if value.isdigit():
            return int(value) > 0
        return len(value) >= 2
    return False


def _coerce_body(body: Any) -> Optional[Any]:
    """dict or list only (_extract_leaf_fields handles both) — a bare JSON
    array response (e.g. absence-app's GET /api/balances: `return [dict(r)
    for r in rows]`, no {"items": [...]} wrapper) must pass through here
    too, not just dict-wrapped payloads, or its fields are never scanned."""
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except Exception:
            return None
    return body if isinstance(body, (dict, list)) else None


def detect_dependencies(
    steps: List[WorkflowStep],
    raw_calls: Optional[List[Any]] = None,
) -> List[WorkflowStep]:
    # ── Pass 1: mutating-step chain (fallback) ───────────────────────────────
    previous_mutating_key: str | None = None
    for step in steps:
        if step.method in {"POST", "PUT", "PATCH", "DELETE"}:
            if previous_mutating_key:
                step.depends_on.append(previous_mutating_key)
            previous_mutating_key = step.canonical_key

    # ── Pass 2: schema-based ID propagation (name-only, single example) ─────
    _detect_schema_dependencies(steps)

    # ── Pass 3: real value correlation across the raw per-call sequence ─────
    if raw_calls:
        _detect_value_dependencies(steps, raw_calls)

    return steps


def _detect_schema_dependencies(steps: List[WorkflowStep]) -> None:
    """
    Scan each POST/PUT step's response_body (stored in step.metadata by
    build_sequence) for id fields, then match them to path params in later steps.

    Mutates steps in-place; duplicate depends_on entries are prevented.
    """
    # field_name → canonical_key of the step that produces it
    produced_ids: Dict[str, str] = {}

    for step in steps:
        if step.method not in {"POST", "PUT"}:
            continue

        response_body = step.metadata.get("response_body")
        if not response_body:
            continue

        if isinstance(response_body, str):
            try:
                response_body = json.loads(response_body)
            except Exception:
                continue

        if not isinstance(response_body, dict):
            continue

        for field in response_body:
            if field == "id" or field.endswith("_id"):
                # First writer wins (stable across repeated calls)
                produced_ids.setdefault(field, step.canonical_key)

    for step in steps:
        for segment in step.path.split("/"):
            if not (segment.startswith("{") and segment.endswith("}")):
                continue
            param_name   = segment[1:-1]
            producer_key = produced_ids.get(param_name)
            if (
                producer_key
                and producer_key != step.canonical_key
                and producer_key not in step.depends_on
            ):
                step.depends_on.append(producer_key)
                logger.debug(
                    "schema_dependency.detected step=%s depends_on=%s via_param=%s",
                    step.canonical_key, producer_key, param_name,
                )


def _extract_leaf_fields(body: Any, _depth: int = 0) -> List[Tuple[str, Any]]:
    """(field_name, value) pairs from a dict's own keys, plus one level of
    nested dicts/lists-of-dicts — enough to catch a foreign key nested one
    level deep (e.g. {"employee": {"id": 2}}) or inside a paginated list
    response (e.g. {"items": [{"id": 1}, {"id": 2}], "total": 2} — the
    {"items": [...] } shape list_employees()/list_requests()/etc. all use)
    without walking arbitrarily deep into unrelated payload structure."""
    if isinstance(body, list):
        # Unwrapping a list (pagination envelope) doesn't count as a nesting
        # level — {"items": [...]} is still "depth 0" data as far as the
        # caller's concerned, not one level deeper.
        out: List[Tuple[str, Any]] = []
        for item in body:
            out.extend(_extract_leaf_fields(item, _depth))
        return out
    if not isinstance(body, dict) or _depth > 1:
        return []
    out = []
    for key, value in body.items():
        if isinstance(value, (dict, list)):
            out.extend(_extract_leaf_fields(value, _depth + 1))
        else:
            out.append((key, value))
    return out


def _detect_value_dependencies(steps: List[WorkflowStep], raw_calls: List[Any]) -> None:
    """Real correlation pass — see module docstring. raw_calls is the
    pre-dedup per-call list (app.normalization.models.NormalizedEndpoint),
    in original capture order, with each call's actual request/response
    body and concrete path-parameter values (not the one merged example
    deduplicate_endpoints() kept)."""
    step_keys = {s.canonical_key for s in steps}
    calls = [c for c in raw_calls if c.canonical_key in step_keys]
    if len(calls) < 2:
        return

    # value → canonical_key of the call whose response produced it (first
    # writer wins — stable across a resource created/read multiple times).
    # Keyed by str(value): a path param is always a string ("1"), but the
    # same id in a JSON response body is typically a number (1) — without
    # normalizing both to the same representation they'd never match.
    produced: Dict[str, str] = {}
    edges: set[Tuple[str, str]] = set()  # (consumer_key, producer_key)

    for call in calls:
        # Consumer side first — a call can't depend on its own later output.
        for param in getattr(call, "path_parameters", []):
            if not _looks_like_id_field(param.name) or not _is_plausible_id_value(param.raw_value):
                continue
            producer_key = produced.get(str(param.raw_value))
            if producer_key and producer_key != call.canonical_key:
                edges.add((call.canonical_key, producer_key))

        request_body = _coerce_body(call.request_body)
        if request_body:
            for field, value in _extract_leaf_fields(request_body):
                if not _looks_like_id_field(field) or not _is_plausible_id_value(value):
                    continue
                producer_key = produced.get(str(value))
                if producer_key and producer_key != call.canonical_key:
                    edges.add((call.canonical_key, producer_key))

        # Producer side — what this call's response hands to later calls.
        response_body = _coerce_body(call.response_body)
        if response_body:
            for field, value in _extract_leaf_fields(response_body):
                if _looks_like_id_field(field) and _is_plausible_id_value(value):
                    produced.setdefault(str(value), call.canonical_key)

    by_key = {s.canonical_key: s for s in steps}
    for consumer_key, producer_key in edges:
        step = by_key.get(consumer_key)
        if step is not None and producer_key not in step.depends_on:
            step.depends_on.append(producer_key)
            logger.debug(
                "value_dependency.detected step=%s depends_on=%s",
                consumer_key, producer_key,
            )
