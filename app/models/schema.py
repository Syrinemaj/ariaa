from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import OrgScopedMixin


class EndpointSchema(OrgScopedMixin, Base):
    __tablename__ = "endpoint_schemas"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    endpoint_id: Mapped[str] = mapped_column(String, ForeignKey("endpoints.id"), nullable=False)
    request_schema: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    response_schema: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status_codes: Mapped[list] = mapped_column(ARRAY(Integer), default=list)
    auth_required: Mapped[bool] = mapped_column(Boolean, default=False)
    auth_type: Mapped[str | None] = mapped_column(String, nullable=True)
    auth_location: Mapped[str | None] = mapped_column(String, nullable=True)
    auth_header_name: Mapped[str | None] = mapped_column(String, nullable=True)
    auth_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    endpoint = relationship("Endpoint", back_populates="schema")
