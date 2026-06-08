"""
Process-wide context variables propagated across async tasks.

current_request_id is set by the add_request_id middleware in main.py and
read by any code that wants to correlate logs and LLM calls to a single
HTTP request, even if that code is several async call-frames away.
"""
from __future__ import annotations

from contextvars import ContextVar

current_request_id: ContextVar[str] = ContextVar("request_id", default="unknown")
