from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class BulkBatch(Base):
    __tablename__ = "bulk_batches"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    automation_run_id: Mapped[str] = mapped_column(String, nullable=False)
    batch_number: Mapped[int] = mapped_column(Integer, nullable=False)
    start_row: Mapped[int] = mapped_column(Integer, default=0)
    end_row: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String, default="running")
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    batch_rows = relationship("BulkBatchRow", back_populates="batch", cascade="all, delete-orphan")


class BulkBatchRow(Base):
    __tablename__ = "bulk_batch_rows"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    batch_id: Mapped[str] = mapped_column(String, ForeignKey("bulk_batches.id"), nullable=False)
    data_row_id: Mapped[str] = mapped_column(String, nullable=False)
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    result_json: Mapped[dict] = mapped_column(JSONB, default=dict)

    batch = relationship("BulkBatch", back_populates="batch_rows")
