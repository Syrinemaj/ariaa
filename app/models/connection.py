from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrgScopedMixin, TimestampMixin


class Connection(TimestampMixin, OrgScopedMixin, Base):
    """How ARIA authenticates to a target system at execution time —
    replaces the free-text base_url/auth_headers passed per-call today
    (see Phase 1: that path currently puts secrets in Celery task args).
    encrypted_secret is a Fernet token (app/connections/crypto.py) — the
    plaintext shape behind it depends on auth_type and is only ever
    reconstructed inside the Celery worker, right before the HTTP call."""

    __tablename__ = "connections"
    __table_args__ = (UniqueConstraint("org_id", "name", name="uq_connections_org_id_name"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String, nullable=False)
    base_url: Mapped[str] = mapped_column(String, nullable=False)
    environment: Mapped[str] = mapped_column(String, nullable=False)  # test | preprod | prod
    auth_type: Mapped[str] = mapped_column(String, nullable=False)    # service_account | oauth_client_credentials | api_key
    encrypted_secret: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")  # active | revoked
    secret_rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True)


class ConnectionOperator(Base):
    """Which operators may select a given connection — admins implicitly
    may use any connection in their org, this table only restricts
    operators (see app/connections/service.py::list_usable_connections)."""

    __tablename__ = "connection_operators"
    __table_args__ = (
        UniqueConstraint("connection_id", "user_id", name="uq_connection_operators_connection_id_user_id"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    connection_id: Mapped[str] = mapped_column(String, ForeignKey("connections.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
