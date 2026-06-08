"""
AI usage reporter — emits daily summary as structured log (Fix 14.3).

Replaces the print() block so the output flows through structlog's JSON
pipeline and gets captured by log aggregators (Loki, CloudWatch, etc.)
instead of disappearing into stdout.
"""
from __future__ import annotations

from app.core.logging import get_logger

logger = get_logger(__name__)


def log_ai_usage(tokens_today: int, cost_today: float, high_token_calls: int) -> None:
    """Emit daily AI usage summary as a structured INFO log line."""
    logger.info(
        "ai_usage.daily_summary",
        tokens_today=tokens_today,
        cost_today_usd=round(cost_today, 6),
        high_token_calls=high_token_calls,
    )
