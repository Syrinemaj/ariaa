"""
token_guard — payload truncation before LLM submission.

Delegates to token_counter.truncate_dict_to_token_limit() which uses
tiktoken for accurate token counting. Uses the Groq model name for
tiktoken encoding lookup (falls back to cl100k_base for unknown models).
"""
import logging

from app.ai.token_counter import truncate_dict_to_token_limit
from app.core.config import settings

logger = logging.getLogger(__name__)


def truncate_payload(payload: dict) -> tuple[dict, bool]:
    """
    Truncate a dict payload so it fits within LLM_MAX_INPUT_TOKENS.
    Returns (safe_payload, was_truncated).
    """
    safe, truncated = truncate_dict_to_token_limit(
        payload=payload,
        model=settings.GROQ_MODEL,
        max_tokens=settings.LLM_MAX_INPUT_TOKENS,
    )
    if truncated:
        logger.warning(
            "token_guard: payload truncated to fit model context window "
            "(model=%s, limit=%d tokens)",
            settings.GROQ_MODEL,
            settings.LLM_MAX_INPUT_TOKENS,
        )
    return safe, truncated
