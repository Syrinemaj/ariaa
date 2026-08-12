from uuid import uuid4

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import OrgScopedMixin, TimestampMixin, UserOwnedMixin


class Notification(TimestampMixin, OrgScopedMixin, UserOwnedMixin, Base):
    """
    Two audiences, distinguished by recipient_user_id:
      - NULL            -> team-wide: every ADMIN sharing org_id (an operator
                            launched a bulk run — see create_bulk_launch_notification)
      - a specific user  -> that user only (their own bulk run finished — see
                            create_run_completed_notification)
    created_by_user_id is always the operator whose action is being reported.
    """
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    action: Mapped[str] = mapped_column(String, nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String, nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String, nullable=True)
    har_file_name: Mapped[str | None] = mapped_column(String, nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    recipient_user_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("users.id"), nullable=True, index=True,
    )

    actor = relationship("User", foreign_keys="Notification.created_by_user_id")
