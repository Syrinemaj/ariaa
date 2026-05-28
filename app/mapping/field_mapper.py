from typing import Any, Dict, List


def normalize_field_name(value: str) -> str:
    value = value.strip()
    value = value.replace("-", "_").replace(" ", "_")
    return value.lower()


def to_camel_case(value: str) -> str:
    parts = normalize_field_name(value).split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


def candidate_names(source_field: str) -> set[str]:
    normalized = normalize_field_name(source_field)
    return {
        source_field,
        normalized,
        to_camel_case(source_field),
        normalized.replace("_", ""),
    }


def apply_mapping_to_row(
    row: Dict[str, Any],
    mappings: List[Dict[str, Any]],
) -> Dict[str, Any]:
    mapped: Dict[str, Any] = {}

    for mapping in mappings:
        source_field = mapping["source_field"]
        target_field = mapping["target_field"]

        if source_field in row:
            mapped[target_field] = row[source_field]

    return mapped
