from typing import Any, Dict, List, Optional

from app.schema_inference.models import InferredSchema


def _as_type_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        return [value]
    return ["string"]


def merge_property_schema(existing: dict, new: dict) -> dict:
    if not existing:
        return new

    if existing.get("type") == new.get("type"):
        if existing.get("type") == "object":
            return {
                "type": "object",
                "properties": merge_properties(
                    existing.get("properties", {}),
                    new.get("properties", {}),
                ),
                "required": list(
                    set(existing.get("required", [])) & set(new.get("required", []))
                ),
            }
        if existing.get("type") == "array":
            return {
                "type": "array",
                "items": merge_property_schema(
                    existing.get("items", {}),
                    new.get("items", {}),
                ),
            }
        return existing

    return {
        "type": sorted(list(set(_as_type_list(existing.get("type")) + _as_type_list(new.get("type")))))
    }


def merge_properties(existing: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(existing)
    for key, new_schema in new.items():
        if key not in merged:
            merged[key] = new_schema
        else:
            merged[key] = merge_property_schema(merged[key], new_schema)
    return merged


def merge_schemas(
    existing: Optional[InferredSchema],
    new: Optional[InferredSchema],
) -> Optional[InferredSchema]:
    if existing is None:
        return new
    if new is None:
        return existing

    return InferredSchema(
        type=existing.type,
        properties=merge_properties(existing.properties, new.properties),
        required=list(set(existing.required) & set(new.required)),
    )
