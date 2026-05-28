from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class BulkValidationRun(Base):
    __tablename__ = "bulk_validation_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    data_file_id: Mapped[str] = mapped_column(String, ForeignKey("data_files.id"), nullable=False)
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    valid_rows: Mapped[int] = mapped_column(Integer, default=0)
    invalid_rows: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String, default="running")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    errors = relationship("BulkValidationError", back_populates="validation_run", cascade="all, delete-orphan")


class BulkValidationError(Base):
    __tablename__ = "bulk_validation_errors"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    validation_run_id: Mapped[str] = mapped_column(String, ForeignKey("bulk_validation_runs.id"), nullable=False)
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)
    field_name: Mapped[str | None] = mapped_column(String, nullable=True)
    error_code: Mapped[str] = mapped_column(String, nullable=False)
    message: Mapped[str] = mapped_column(String, nullable=False)

    validation_run = relationship("BulkValidationRun", back_populates="errors")
