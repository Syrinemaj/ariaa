from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import OrgScopedMixin, UserOwnedMixin


class DataFile(OrgScopedMixin, UserOwnedMixin, Base):
    __tablename__ = "data_files"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    analysis_run_id: Mapped[str] = mapped_column(String, ForeignKey("analysis_runs.id"), nullable=False)
    file_name: Mapped[str] = mapped_column(String, nullable=False)
    file_type: Mapped[str] = mapped_column(String, nullable=False)
    rows_count: Mapped[int] = mapped_column(Integer, default=0)
    columns: Mapped[list] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String, default="parsed")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    rows = relationship("DataRow", back_populates="data_file", cascade="all, delete-orphan")


class DataRow(Base):
    __tablename__ = "data_rows"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    data_file_id: Mapped[str] = mapped_column(String, ForeignKey("data_files.id"), nullable=False)
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_data: Mapped[dict] = mapped_column(JSONB, default=dict)
    normalized_data: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String, default="pending")
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)

    data_file = relationship("DataFile", back_populates="rows")
