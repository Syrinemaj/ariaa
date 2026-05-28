from typing import Any, Dict

from app.reference_resolution.lookup_builder import build_static_lookup


def resolve_references_for_row(mapped_row: Dict[str, Any]) -> Dict[str, Any]:
    lookup = build_static_lookup()
    resolved = dict(mapped_row)

    for target_field, values in lookup.items():
        if target_field in resolved:
            raw_value = resolved[target_field]
            if isinstance(raw_value, str) and raw_value in values:
                resolved[target_field] = values[raw_value]

    return resolved
