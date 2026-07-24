"""
Workflow dependency detection — two-pass, no LLM required.

Pass 1 (unchanged): a mutating step (POST/PUT/PATCH/DELETE) depends on the
  previous mutating step in the sequence.

Pass 2 (new): schema-based detection — if a POST or PUT step's response body
  contains a field named "id" or ending in "_id", and a later step's path
  contains a matching {param} placeholder, the later step depends on the
  creator step.

Example:
  POST /users → response: {"user_id": 42}
  GET  /users/{user_id} → path param {user_id} matches "user_id" produced above
  → GET step gains depends_on = ["POST /users canonical_key"]
"""
from __future__ import annotations

import json
import logging
from typing import Dict, List

from app.workflows.models import WorkflowStep

logger = logging.getLogger(__name__)


def detect_dependencies(steps: List[WorkflowStep]) -> List[WorkflowStep]:
    # ── Pass 1: mutating-step chain ──────────────────────────────────────────
    previous_mutating_key: str | None = None
    for step in steps:
        if step.method in {"POST", "PUT", "PATCH", "DELETE"}:
            if previous_mutating_key:
                step.depends_on.append(previous_mutating_key)
            previous_mutating_key = step.canonical_key

    # ── Pass 2: schema-based ID propagation ─────────────────────────────────
    _detect_schema_dependencies(steps)

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
