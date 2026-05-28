from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LLMCall(Base):
    __tablename__ = "llm_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_name: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, nullable=False)
    is_high_token: Mapped[bool] = mapped_column(default=False)
    called_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
