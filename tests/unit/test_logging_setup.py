"""
Unit tests — core/logging.py + core/context.py (Section 14.2/14.3).
"""
from __future__ import annotations

import structlog

from app.core.context import current_request_id
from app.core.logging import get_logger, setup_logging


class TestSetupLogging:
    def test_setup_logging_does_not_raise(self):
        setup_logging()  # idempotent

    def test_get_logger_returns_bound_logger(self):
        setup_logging()
        logger = get_logger("test.module")
        assert logger is not None

    def test_logger_has_info_method(self):
        setup_logging()
        logger = get_logger("test.module")
        assert callable(getattr(logger, "info", None))

    def test_logger_has_warning_method(self):
        setup_logging()
        logger = get_logger("test.module")
        assert callable(getattr(logger, "warning", None))


class TestRequestIdContextVar:
    def test_default_value_is_unknown(self):
        assert current_request_id.get() == "unknown"

    def test_set_and_get_roundtrip(self):
        token = current_request_id.set("req-abc-123")
        try:
            assert current_request_id.get() == "req-abc-123"
        finally:
            current_request_id.reset(token)

    def test_reset_restores_default(self):
        token = current_request_id.set("req-xyz")
        current_request_id.reset(token)
        assert current_request_id.get() == "unknown"
