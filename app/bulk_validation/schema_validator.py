from typing import Any, Dict, List


def validate_row_against_plan(
    row: Dict[str, Any],
    plan: Dict[str, Any],
    row_index: int,
) -> List[Dict[str, Any]]:
    errors = []

    for step in plan.get("steps", []):
        request_schema = step.get("request_schema") or {}
        for field in request_schema.get("required", []):
            if field not in row or row[field] in {None, ""}:
                errors.append({
                    "row_index": row_index,
                    "field_name": field,
                    "error_code": "MISSING_REQUIRED_FIELD",
                    "message": f"Missing required field: {field}",
                    "endpoint": step.get("canonical_key"),
                })

    return errors
