from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrgScopedMixin, TimestampMixin

DEFAULT_ENVIRONMENT_POLICIES = {
    "test": "full_access",
    "preprod": "full_access",
    "prod": "full_access",
}


class GovernancePolicy(TimestampMixin, OrgScopedMixin, Base):
    """Singleton per org (see uq_governance_policies_org_id) — the admin-
    configured risk thresholds and per-environment policy that
    app/governance/policy_engine.py::check_execution_policy() evaluates
    every plan against. Defaults reproduce pre-governance behavior (see
    app/governance/service.py::get_or_create_policy)."""

    __tablename__ = "governance_policies"
    __table_args__ = (UniqueConstraint("org_id", name="uq_governance_policies_org_id"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    risk_threshold_low: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    risk_threshold_high: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    environment_policies: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=lambda: dict(DEFAULT_ENVIRONMENT_POLICIES)
    )
    updated_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True)


class ForbiddenEndpointRule(OrgScopedMixin, Base):
    """One admin-defined rule, e.g. method='DELETE', path_pattern='/employees/*'
    (fnmatch-style — see app/governance/policy_engine.py). method=None matches
    any HTTP method on that path pattern."""

    __tablename__ = "forbidden_endpoint_rules"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    method: Mapped[str | None] = mapped_column(String, nullable=True)
    path_pattern: Mapped[str] = mapped_column(String, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
