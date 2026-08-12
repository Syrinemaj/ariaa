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

from typing import Any


def strip_null_bytes(value: Any) -> Any:
    if isinstance(value, str):
        return value.replace("\x00", "") if "\x00" in value else value
    if isinstance(value, dict):
        return {key: strip_null_bytes(item) for key, item in value.items()}
    if isinstance(value, list):
        return [strip_null_bytes(item) for item in value]
    return value
