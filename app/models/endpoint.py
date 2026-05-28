from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import OrgScopedMixin


class Endpoint(OrgScopedMixin, Base):
    __tablename__ = "endpoints"
    __table_args__ = (
        # Prevent duplicate endpoints within the same analysis run per org.
        # canonical_key already embeds org_id (build_registry_key), but this
        # DB constraint adds a hard guarantee even if that ever changes.
        UniqueConstraint("org_id", "canonical_key", "run_id", name="uq_endpoints_org_canonical_run"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str] = mapped_column(String, ForeignKey("analysis_runs.id"), nullable=False)
    method: Mapped[str] = mapped_column(String, nullable=False)
    path: Mapped[str] = mapped_column(String, nullable=False)
    # Org-scoped canonical key: "{org_id}:METHOD /path"
    canonical_key: Mapped[str] = mapped_column(String, nullable=False, index=True)
    source_count: Mapped[int] = mapped_column(Integer, default=1)
    business_domain: Mapped[str | None] = mapped_column(String, nullable=True)
    business_action: Mapped[str | None] = mapped_column(String, nullable=True)
    path_parameters: Mapped[dict] = mapped_column(JSONB, default=list)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    analysis_run = relationship("AnalysisRun", back_populates="endpoints")
    schema = relationship(
        "EndpointSchema",
        back_populates="endpoint",
        uselist=False,
        cascade="all, delete-orphan",
    )
