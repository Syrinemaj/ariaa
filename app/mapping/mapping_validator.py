from typing import Any, Dict, List


def validate_mappings(
    mappings: List[Dict[str, Any]],
    plan: Dict[str, Any],
) -> Dict[str, Any]:
    required_fields = []

    for step in plan.get("steps", []):
        request_schema = step.get("request_schema") or {}
        for field in request_schema.get("required", []):
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
