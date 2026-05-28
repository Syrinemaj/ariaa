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


def map_payload_for_step(
    step: PlanStep,
    input_row: Dict[str, Any],
    state: Dict[str, Any],
) -> Dict[str, Any]:
    if not step.request_schema:
        return {}

    properties = step.request_schema.get("properties", {})
    payload: Dict[str, Any] = {}

    for field_name in properties.keys():
        candidates = _candidate_keys(field_name)
        for candidate in candidates:
            if candidate in input_row:
                payload[field_name] = input_row[candidate]
                break
            if candidate in state:
                payload[field_name] = state[candidate]
                break

    return payload
