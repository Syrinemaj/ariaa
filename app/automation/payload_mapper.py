from typing import Any, Dict, List

from app.planner.models import PlanStep


def _to_snake_case(value: str) -> str:
    result = ""
    for index, char in enumerate(value):
        if char.isupper() and index > 0:
            result += "_"
        result += char.lower()
    return result.replace("-", "_")


def _candidate_keys(schema_field: str) -> List[str]:
    snake = _to_snake_case(schema_field)
    return list({schema_field, snake, schema_field.lower(), snake.replace("_", "")})


def _coerce_value(value: Any, field_schema: Dict[str, Any]) -> Any:
    """Coerce value to match the JSON Schema type declared for the field.

    CSV rows and API responses often carry integers where the schema says
    "string" (e.g. departmentId: 10 vs type: "string").  Silently convert
    rather than failing with a jsonschema type error at execution time.
    """
    expected = field_schema.get("type")
    if expected == "string" and not isinstance(value, str):
        return str(value)
    if expected == "integer" and isinstance(value, str):
        try:
            return int(value)
        except (ValueError, TypeError):
            return value
    if expected == "number" and isinstance(value, str):
        try:
            return float(value)
        except (ValueError, TypeError):
            return value
    if expected == "boolean" and isinstance(value, str):
        return value.lower() in ("true", "1", "yes")
    return value


def map_payload_for_step(
    step: PlanStep,
    input_row: Dict[str, Any],
    state: Dict[str, Any],
) -> Dict[str, Any]:
    if not step.request_schema:
        return {}

    properties = step.request_schema.get("properties", {})
    payload: Dict[str, Any] = {}

    for field_name, field_schema in properties.items():
        candidates = _candidate_keys(field_name)
        for candidate in candidates:
            if candidate in input_row:
                payload[field_name] = _coerce_value(input_row[candidate], field_schema)
                break
            if candidate in state:
                payload[field_name] = _coerce_value(state[candidate], field_schema)
                break

    return payload
