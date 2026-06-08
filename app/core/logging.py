"""
Structured logging — JSON lines via structlog.

Every log line emits: timestamp, level, logger, request_id (from ContextVar),
plus any fields passed at the call site.

Usage:
    from app.core.logging import get_logger
    logger = get_logger(__name__)
    logger.info("endpoint.found", path="/users/{id}", method="GET")
    logger.warning("token_guard.truncation", max_chars=32000, original=50000)

Call setup_logging() ONCE at application startup (before any imports that log).
"""
from __future__ import annotations

import logging

import structlog


def setup_logging() -> None:
    """Configure structlog with ISO timestamps, log level, and JSON output."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger scoped to `name` (pass __name__)."""
    return structlog.get_logger(name)
