"""
Shared step-ordering logic for both plan generation paths — RAG-based
instruction plans (plan_builder.py) and workflow-to-plan conversion
(app/api/automation.py::plan_from_workflow).

Both paths previously left `depends_on` empty (RAG path never computed it;
workflow-to-plan discarded the real value at conversion time), and neither
path guaranteed that `step.order` actually respects dependencies — steps
were ordered by RAG relevance score or raw workflow-detection order, not by
"what must happen before what". This module fixes both: schema-based
dependency detection for steps that only have a JSON schema (not a sample
response body like workflow detection has), and a topological sort so the
final `order` is always execution-safe.
"""
from __future__ import annotations

from typing import Any, Dict, List


class DependencyCycleError(Exception):
    """Raised when depends_on forms a cycle. Should not happen from real
    detection logic (an endpoint can't consume an ID it itself hasn't
    produced yet), but a plan must never silently execute in a broken order
    if it somehow does."""


def detect_schema_dependencies(steps: List[Dict[str, Any]]) -> None:
    """
    Mutates `steps` in place, appending to each step's "depends_on" list.

    Same idea as app/workflows/dependency_detector.py::_detect_schema_dependencies
    (if a POST/PUT step's response contains an "id"/"*_id" field, and a later
    step's path has a matching {param}, the latter depends on the former) —
    but adapted for steps whose "response_schema" is a JSON SCHEMA
    ({"type": "object", "properties": {...}}), not a sample response body.

    Deliberately does NOT apply workflow detection's Pass 1 (chain each
    mutating step to the previous mutating step) — that pass assumes step
    order is chronological (real observed traffic), which holds for detected
    workflows but not for RAG-ranked steps (ordered by semantic relevance,
    not execution history). Chaining on that order would fabricate
    dependencies that don't actually exist.
    """
    produced_ids: Dict[str, str] = {}

    for step in steps:
        if step.get("method", "").upper() not in {"POST", "PUT"}:
            continue
        properties = (step.get("response_schema") or {}).get("properties", {})
        if not isinstance(properties, dict):
            continue
        for field in properties:
            if field == "id" or field.endswith("_id"):
                produced_ids.setdefault(field, step["canonical_key"])

    for step in steps:
        depends_on = step.setdefault("depends_on", [])
        for segment in step.get("path", "").split("/"):
            if not (segment.startswith("{") and segment.endswith("}")):
                continue
            param_name = segment[1:-1]
            producer_key = produced_ids.get(param_name)
            if (
                producer_key
                and producer_key != step["canonical_key"]
                and producer_key not in depends_on
            ):
                depends_on.append(producer_key)


def topological_sort_steps(steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Reorders `steps` so every dependency appears before its dependent
    (Kahn's algorithm, stable — ties broken by original input order).

    Dangling depends_on entries (referencing a canonical_key not present in
    `steps`) are ignored here, not raised — that's a separate concern,
    checked explicitly in plan_validator.py so it surfaces as a visible
    PlanValidationIssue rather than a silent no-op or a crash here.

    Raises DependencyCycleError if depends_on forms a cycle.
    """
    by_key = {s["canonical_key"]: s for s in steps}
    in_degree: Dict[str, int] = {s["canonical_key"]: 0 for s in steps}
    dependents: Dict[str, List[str]] = {s["canonical_key"]: [] for s in steps}

    for step in steps:
        key = step["canonical_key"]
        for dep in step.get("depends_on") or []:
            if dep not in by_key or dep == key:
                continue
            dependents[dep].append(key)
            in_degree[key] += 1

    order_index = {s["canonical_key"]: i for i, s in enumerate(steps)}
    ready = sorted(
        (k for k, deg in in_degree.items() if deg == 0),
        key=lambda k: order_index[k],
    )
    result: List[str] = []
    while ready:
        ready.sort(key=lambda k: order_index[k])
        key = ready.pop(0)
        result.append(key)
        for dependent in dependents[key]:
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                ready.append(dependent)

    if len(result) != len(steps):
        remaining = [k for k in in_degree if k not in result]
        raise DependencyCycleError(
            f"Circular dependency detected among plan steps: {remaining}"
        )

    ordered = [by_key[k] for k in result]
    for index, step in enumerate(ordered, start=1):
        step["order"] = index
    return ordered
