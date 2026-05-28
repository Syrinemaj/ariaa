from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    org_id: Mapped[str] = mapped_column(
        String,
        nullable=False,
        index=True,
    )

    # Nullable : permet de logguer les tentatives de connexion échouées
    # sans user object (user inconnu ou inexistant)
    user_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )

    action: Mapped[str] = mapped_column(
        String,
        nullable=False,
        index=True,
    )

    resource_type: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
        index=True,
    )

    resource_id: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
        index=True,
    )

    metadata_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        index=True,
    )
