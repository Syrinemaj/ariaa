from typing import Any, Dict, List, Optional, Set

from app.automation.payload_mapper import required_input_fields
from app.planner.models import AutomationPlan


def plan_needed_fields(plan: Dict[str, Any]) -> Set[str]:
    """Field names the CSV/row must actually supply for this plan — i.e. NOT
    auto-resolved from an earlier step's response (employee_id after a
    "Create Employee" step, etc.). Computed once per plan by the caller
    (see validate_bulk_data) and passed into validate_row_against_plan for
    every row, rather than recomputed per row.

    Reuses required_input_fields() (app/automation/payload_mapper.py) —
    same static analysis that drives the "Fields your input JSON needs" /
    "Columns your CSV needs" UI, so the validator can never flag a field as
    missing that the UI already told the operator they didn't need to
    provide. Before this, validate_row_against_plan checked every step's
    schema-required fields literally against the row with no such
    exclusion, so any multi-step plan with a cross-step foreign key
    (employee_id, contract_id, ...) marked EVERY row invalid — the plan
    would still have executed correctly (map_payload_for_step resolves it
    from state at run time), but validation blocked it from ever getting
    there.
    """
    return {f["field"] for f in required_input_fields(AutomationPlan.model_validate(plan))}


def validate_row_against_plan(
    row: Dict[str, Any],
    plan: Dict[str, Any],
    row_index: int,
    needed_fields: Optional[Set[str]] = None,
) -> List[Dict[str, Any]]:
    errors = []
    if needed_fields is None:
        needed_fields = plan_needed_fields(plan)

    for step in plan.get("steps", []):
        request_schema = step.get("request_schema") or {}
        for field in request_schema.get("required", []):
            if field not in needed_fields:
                continue  # auto-resolved from an earlier step's response at execution time
            if field not in row or row[field] in {None, ""}:
                errors.append({
                    "row_index": row_index,
                    "field_name": field,
                    "error_code": "MISSING_REQUIRED_FIELD",
                    "message": f"Missing required field: {field}",
                    "endpoint": step.get("canonical_key"),
                })

    return errors
