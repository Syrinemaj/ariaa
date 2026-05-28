from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FieldMapping(Base):
    __tablename__ = "field_mappings"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    analysis_run_id: Mapped[str] = mapped_column(String, nullable=False)
    source_field: Mapped[str] = mapped_column(String, nullable=False)
    target_field: Mapped[str] = mapped_column(String, nullable=False)
    target_endpoint_key: Mapped[str | None] = mapped_column(String, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    source: Mapped[str] = mapped_column(String, default="rules")
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
