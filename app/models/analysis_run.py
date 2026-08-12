from uuid import uuid4

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import OrgScopedMixin, TeamScopedMixin, TimestampMixin, UserOwnedMixin


class AnalysisRun(TimestampMixin, OrgScopedMixin, UserOwnedMixin, TeamScopedMixin, Base):
    __tablename__ = "analysis_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    file_name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="processing")
    total_cleaned_api_calls: Mapped[int] = mapped_column(Integer, default=0)
    total_normalized_endpoints: Mapped[int] = mapped_column(Integer, default=0)
    total_schema_results: Mapped[int] = mapped_column(Integer, default=0)

    endpoints = relationship("Endpoint", back_populates="analysis_run", cascade="all, delete-orphan")
    workflows = relationship("WorkflowModel", back_populates="analysis_run", cascade="all, delete-orphan")
