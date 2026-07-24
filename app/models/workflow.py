from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class WorkflowModel(Base):
    __tablename__ = "workflows"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str] = mapped_column(String, ForeignKey("analysis_runs.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    business_domain: Mapped[str | None] = mapped_column(String, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    schema_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # ARIA-WORKFLOW-V2: added for automatic "find an existing workflow
    # matching this intent" lookup in the planner (migration 013). NULL on
    # existing rows for primary_entity/action — no derivable source, to be
    # populated by a future enrichment step. org_id is backfilled in the
    # migration from analysis_runs.org_id via run_id.
    primary_entity: Mapped[str | None] = mapped_column(String(100), nullable=True)
    action: Mapped[str | None] = mapped_column(String(100), nullable=True)
    org_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("organizations.id"), nullable=True, index=True
    )

    analysis_run = relationship("AnalysisRun", back_populates="workflows")
    steps = relationship("WorkflowStepModel", back_populates="workflow", cascade="all, delete-orphan")


class WorkflowStepModel(Base):
    __tablename__ = "workflow_steps"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    workflow_id: Mapped[str] = mapped_column(String, ForeignKey("workflows.id"), nullable=False)
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    method: Mapped[str] = mapped_column(String, nullable=False)
    path: Mapped[str] = mapped_column(String, nullable=False)
    canonical_key: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[str | None] = mapped_column(String, nullable=True)
    depends_on: Mapped[list] = mapped_column(JSONB, default=list)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)

    workflow = relationship("WorkflowModel", back_populates="steps")
