from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AutomationApproval(Base):
    __tablename__ = "automation_approvals"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    automation_run_id: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, default="pending")
    approved_by: Mapped[str | None] = mapped_column(String, nullable=True)
    comment: Mapped[str | None] = mapped_column(String, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
