"""
Schema drift detection — guards automation plans against silent API changes.

At plan creation time, call build_schema_snapshot() and store the result in
AutomationPlan.metadata["schema_snapshot"]. At execution start, call
check_schema_drift() to compare the snapshot against current endpoints.

Breaking drift → abort execution, notify user.
Non-breaking drift → log warning, continue.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Literal

from app.models.endpoint import Endpoint
from app.planner.models import AutomationPlan


@dataclass
class SchemaDriftWarning:
    endpoint_key: str
    drift_type: Literal["new_required_field", "field_removed", "type_changed"]
    field_name: str
    old_value: Any
    new_value: Any
    is_breaking: bool


async def check_schema_drift(
    plan: AutomationPlan,
    current_endpoints: List[Endpoint],
) -> List[SchemaDriftWarning]:
    """
    Compare schema_snapshot stored at plan creation against current endpoints.

    Schema format expected in snapshot / endpoint.metadata_json:
        {
            "fields": {"field_name": "type_string", ...},
            "required": ["field_name", ...]
        }

    Drift rules:
    - field_removed + was required → breaking
    - field_removed + was optional → non-breaking
    - type_changed → breaking (consumers break on wrong type)
    - new_required_field not in old schema → breaking
    - endpoint entirely missing → breaking

    Returns warnings sorted by severity (breaking first).
    """
    snapshot: Dict[str, Any] = plan.metadata.get("schema_snapshot", {})
    if not snapshot:
        return []

    current_map: Dict[str, Endpoint] = {
        ep.canonical_key: ep for ep in current_endpoints
    }
    warnings: List[SchemaDriftWarning] = []

    for step in plan.steps:
        key = step.canonical_key
        old_schema: Dict[str, Any] = snapshot.get(key, {})
        if not old_schema:
            continue

        current_ep = current_map.get(key)
        if current_ep is None:
            warnings.append(SchemaDriftWarning(
                endpoint_key=key,
                drift_type="field_removed",
                field_name="*",
                old_value=old_schema,
                new_value=None,
                is_breaking=True,
            ))
            continue

        new_schema: Dict[str, Any] = current_ep.metadata_json or {}
        old_fields: Dict[str, str] = old_schema.get("fields", {})
        new_fields: Dict[str, str] = new_schema.get("fields", {})
        old_required: List[str] = old_schema.get("required", [])
        new_required: List[str] = new_schema.get("required", [])

        # Fields present in old but missing in new
        for field_name, old_type in old_fields.items():
            if field_name not in new_fields:
                was_required = field_name in old_required
                warnings.append(SchemaDriftWarning(
                    endpoint_key=key,
                    drift_type="field_removed",
                    field_name=field_name,
                    old_value=old_type,
                    new_value=None,
                    is_breaking=was_required,
                ))
            elif new_fields[field_name] != old_type:
                warnings.append(SchemaDriftWarning(
                    endpoint_key=key,
                    drift_type="type_changed",
                    field_name=field_name,
                    old_value=old_type,
                    new_value=new_fields[field_name],
                    is_breaking=True,
                ))

        # New required fields that callers don't know about
        for field_name in new_required:
            if field_name not in old_required and field_name not in old_fields:
                warnings.append(SchemaDriftWarning(
                    endpoint_key=key,
                    drift_type="new_required_field",
                    field_name=field_name,
                    old_value=None,
                    new_value=new_fields.get(field_name),
                    is_breaking=True,
                ))

    return sorted(warnings, key=lambda w: (not w.is_breaking, w.endpoint_key))


def build_schema_snapshot(endpoints: List[Endpoint]) -> Dict[str, Any]:
    """
    Capture endpoint schemas at plan-creation time.

    Store the returned dict in plan.metadata["schema_snapshot"] so
    check_schema_drift() can compare it later.
    """
    return {
        ep.canonical_key: ep.metadata_json or {}
        for ep in endpoints
    }
