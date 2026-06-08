"""
LLMCall — stores every Azure OpenAI call for cost tracking and correlation.

Fix 14.2: request_id ties a call to the originating HTTP request (via the
X-Request-ID header). celery_task_id ties async Celery task calls to their
task ID so distributed traces can be reconstructed end-to-end.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LLMCall(Base):
    __tablename__ = "llm_calls"
    __table_args__ = (
        # Fast lookup by request_id for distributed tracing and cost attribution
        Index("ix_llm_calls_request_id", "request_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_name: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, nullable=False)
    is_high_token: Mapped[bool] = mapped_column(default=False)
    request_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    celery_task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    estimated_prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    called_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
