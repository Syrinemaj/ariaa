"""
Token-accurate truncation using tiktoken.

Replaces the char-count heuristic (1 token ≈ 4 chars) which is wrong for:
  - JSON payloads (braces, quotes inflate char count vs tokens)
  - Non-ASCII text (UTF-8 multibyte chars counted as 1 char but may be 1+ tokens)
  - Code snippets (identifiers are often single tokens despite many chars)

Requires: pip install tiktoken
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache

logger = logging.getLogger(__name__)

# Fallback char limit when tiktoken is unavailable (conservative: 4 chars/token)
_CHAR_FALLBACK_RATIO = 4


@lru_cache(maxsize=4)
def _get_encoding(model: str):
    """Cache the encoding object — loading it is expensive (few hundred ms)."""
    try:
        import tiktoken
        try:
            return tiktoken.encoding_for_model(model)
        except KeyError:
            # Unknown model — use the cl100k_base encoding (GPT-4 family default)
            return tiktoken.get_encoding("cl100k_base")
    except ImportError:
        return None


def count_tokens(text: str, model: str = "gpt-4o-mini") -> int:
    enc = _get_encoding(model)
    if enc is None:
        return len(text) // _CHAR_FALLBACK_RATIO
    return len(enc.encode(text))


def truncate_to_token_limit(
    text: str,
    model: str,
    max_tokens: int,
) -> tuple[str, bool]:
    """
    Truncate `text` to at most `max_tokens` tokens.

    For JSON strings: truncates at the nearest complete top-level JSON value
    boundary so the result remains valid JSON when possible.
    For plain text: truncates at the last whitespace before the token boundary.

    Returns (truncated_text, was_truncated).
    """
    enc = _get_encoding(model)

    if enc is None:
        # tiktoken unavailable — fall back to char limit
        limit = max_tokens * _CHAR_FALLBACK_RATIO
        if len(text) <= limit:
            return text, False
        return text[:limit], True

    tokens = enc.encode(text)
    if len(tokens) <= max_tokens:
        return text, False

    # Decode the allowed token prefix back to text
    truncated = enc.decode(tokens[:max_tokens])

    # Try to find a clean JSON boundary (closing brace / bracket)
    for boundary_char in ("}", "]"):
        pos = truncated.rfind(boundary_char)
        if pos > len(truncated) // 2:  # don't truncate more than half
            candidate = truncated[: pos + 1]
            try:
                json.loads(candidate)
                return candidate, True
            except json.JSONDecodeError:
                pass

    # Fall back to last whitespace boundary to avoid splitting mid-word
    ws_pos = truncated.rfind(" ")
    if ws_pos > 0:
        return truncated[:ws_pos], True

    return truncated, True


def truncate_dict_to_token_limit(
    payload: dict,
    model: str,
    max_tokens: int,
) -> tuple[dict, bool]:
    """
    Serialize `payload` to JSON, truncate to token limit, then deserialize.
    Returns (safe_payload, was_truncated).
    """
    serialized = json.dumps(payload, ensure_ascii=False)
    truncated_str, was_truncated = truncate_to_token_limit(serialized, model, max_tokens)

    if not was_truncated:
        return payload, False

    try:
        return json.loads(truncated_str), True
    except json.JSONDecodeError:
        # Try repairing by cutting to last comma-separated valid structure
        last_comma = truncated_str.rfind(",")
        if last_comma > 0:
            try:
                repaired = truncated_str[:last_comma] + "}"
                return json.loads(repaired), True
            except json.JSONDecodeError:
                pass
        logger.warning("Could not recover valid JSON after truncation; returning minimal payload")
        return {"_truncated": True, "partial": truncated_str[:500]}, True
