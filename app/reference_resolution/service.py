from typing import Any, Dict

from app.reference_resolution.resolver import resolve_references_for_row


def resolve_row_references(mapped_row: Dict[str, Any]) -> Dict[str, Any]:
    return resolve_references_for_row(mapped_row)
