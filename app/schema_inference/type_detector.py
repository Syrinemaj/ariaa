from typing import Any


def detect_json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "string"


def infer_schema_from_value(value: Any) -> dict:
    detected_type = detect_json_type(value)

    if detected_type == "object":
        return infer_schema_from_object(value)
    if detected_type == "array":
        return infer_schema_from_array(value)
    return {"type": detected_type}


def infer_schema_from_array(values: list) -> dict:
    if not values:
        return {"type": "array", "items": {}}

    first_schema = infer_schema_from_value(values[0])
    return {"type": "array", "items": first_schema}


def infer_schema_from_object(data: dict) -> dict:
    properties = {}
    required = []

    for key, value in data.items():
        properties[key] = infer_schema_from_value(value)
        if value is not None:
            required.append(key)

    return {"type": "object", "properties": properties, "required": required}
