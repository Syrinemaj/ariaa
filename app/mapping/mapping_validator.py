from typing import Any, Dict, List

from app.automation.payload_mapper import required_input_fields
from app.planner.models import AutomationPlan


def validate_mappings(
    mappings: List[Dict[str, Any]],
    plan: Dict[str, Any],
) -> Dict[str, Any]:
    # Fields auto-resolved from an earlier step's response (employee_id after
    # a "Create Employee" step, etc.) never need a mapping — excluding them
    # here keeps is_valid/missing_required_fields consistent with the
    # "Columns your CSV needs" UI and the row-level validator.
    needed_fields = {f["field"] for f in required_input_fields(AutomationPlan.model_validate(plan))}

    required_fields = []

    for step in plan.get("steps", []):
        request_schema = step.get("request_schema") or {}
        for field in request_schema.get("required", []):
            if field not in needed_fields:
                continue
            required_fields.append({
                "field": field,
                "endpoint": step.get("canonical_key"),
                "step_order": step.get("order"),
            })

    mapped_targets = {
        m["target_field"]
        for m in mappings
        if m.get("source_field")
    }

    missing = [item for item in required_fields if item["field"] not in mapped_targets]

    return {
        "is_valid": len(missing) == 0,
        "missing_required_fields": missing,
    }
