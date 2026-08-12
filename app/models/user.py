"""
User model — rôles en majuscules.

Migration 008 met à jour les données existantes :
  "admin"    → "ADMIN"
  "operator" → "OPERATOR"

Migration 014 retire le rôle VIEWER (jamais assigné, jamais appliqué).

Comparaisons de rôles (UserRole est str, Enum) :
  current_user.role == UserRole.ADMIN.value  → "ADMIN" == "ADMIN"  ✓
  current_user.role == "ADMIN"               → ✓
  current_user.role == UserRole.ADMIN        → ✓ (str, Enum hérite de str)
"""
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class UserRole(str, Enum):
    ADMIN = "ADMIN"
    OPERATOR = "OPERATOR"

    @classmethod
    def values(cls) -> set[str]:
        return {r.value for r in cls}


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        CheckConstraint(
            "role IN ('ADMIN', 'OPERATOR')",
            name="ck_users_role",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    org_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)

    role: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=UserRole.OPERATOR.value,
        index=True,
    )

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        onupdate=lambda: datetime.now(timezone.utc),
    )

    organization = relationship(
        "Organization",
        back_populates="users",
        foreign_keys=[org_id],
        primaryjoin="User.org_id == Organization.id",
    )
