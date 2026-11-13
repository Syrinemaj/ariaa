"""
PostgreSQL's text/JSONB types cannot store the NUL byte (\\x00 / \\u0000) —
it's a hard limitation of the C-string-based storage, not an encoding issue,
and asyncpg raises UntranslatableCharacterError on insert if one slips through.

Captured HAR response bodies occasionally contain a stray NUL (binary content,
truncated streams, odd server encodings). strip_null_bytes() recursively walks
a JSON-able value and drops NULs from every string before it reaches a JSONB
column — call it on any dict/list built from raw captured HTTP data.
"""
from __future__ import annotations

from typing import Any, Optional


def strip_null_bytes(value: Any) -> Any:
    if isinstance(value, str):
        return value.replace("\x00", "") if "\x00" in value else value
    if isinstance(value, dict):
        return {key: strip_null_bytes(item) for key, item in value.items()}
    if isinstance(value, list):
        return [strip_null_bytes(item) for item in value]
    return value


def strip_wrapping_quotes(value: Optional[str]) -> Optional[str]:
    """
    business_domain/business_action come straight from an LLM tool-call
    response (endpoint_understanding.py, traffic_classification.py) whose
    prompt asks it to "confirm or refine" a value already given in the
    input — models occasionally answer by literally quoting that value
    back (`"human_resources"` as the *content* of the string, not framing),
    inconsistently and only on some calls. Strip one matching pair of
    leading/trailing quote characters rather than trying to prompt this
    away reliably.
    """
    if not isinstance(value, str) or len(value) < 2:
        return value
    if (value[0] == value[-1] == '"') or (value[0] == value[-1] == "'"):
        return value[1:-1].strip() or value
    return value
