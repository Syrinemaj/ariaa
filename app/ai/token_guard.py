"""
token_guard — payload truncation before LLM submission.

Now delegates to token_counter.truncate_dict_to_token_limit() which uses
tiktoken for accurate token counting instead of the old 1 token ≈ 4 chars
heuristic.
"""
import logging

from app.ai.token_counter import truncate_dict_to_token_limit
from app.core.config import settings

logger = logging.getLogger(__name__)


def truncate_payload(payload: dict) -> tuple[dict, bool]:
    """
    Truncate a dict payload so it fits within LLM_MAX_COMPLETION_TOKENS.
    Returns (safe_payload, was_truncated).
    """
    safe, truncated = truncate_dict_to_token_limit(
        payload=payload,
        model=settings.AZURE_OPENAI_MODEL,
        max_tokens=settings.LLM_MAX_INPUT_CHARS // 4,  # kept for compat; replaced by token count
    )
    if truncated:
        logger.warning(
            "token_guard: payload truncated to fit model context window "
            "(model=%s, limit=%d tokens)",
            settings.AZURE_OPENAI_MODEL,
            settings.LLM_MAX_INPUT_CHARS // 4,
        )
    return safe, truncated
