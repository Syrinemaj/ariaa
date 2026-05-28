from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BulkExecutionReport(Base):
    __tablename__ = "bulk_execution_reports"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    automation_run_id: Mapped[str] = mapped_column(String, nullable=False)
    total_requested: Mapped[int] = mapped_column(Integer, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    partial_success_count: Mapped[int] = mapped_column(Integer, default=0)
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    row_errors: Mapped[list] = mapped_column(JSONB, default=list)
    batch_summary: Mapped[list] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
