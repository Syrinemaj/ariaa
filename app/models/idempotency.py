from uuid import uuid4

from sqlalchemy import Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin


class IdempotencyRecord(TimestampMixin, Base):
    __tablename__ = "idempotency_records"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    automation_run_id: Mapped[str] = mapped_column(String, nullable=False)
    data_row_id: Mapped[str | None] = mapped_column(String, nullable=True)
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)
    endpoint_key: Mapped[str] = mapped_column(String, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    response_reference: Mapped[dict] = mapped_column(JSONB, default=dict)
