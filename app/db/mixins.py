"""
SQLAlchemy mixins partagés par tous les modèles.

TimestampMixin
  Raison : datetime.utcnow() est déprécié en Python 3.12+ et retourne
  une datetime naïve (sans timezone). Toutes les colonnes TIMESTAMP
  doivent être TIMESTAMPTZ en PostgreSQL pour éviter les bugs à
  l'heure d'été et les comparaisons inter-timezone incorrectes.

OrgScopedMixin / UserOwnedMixin
  Multi-tenancy : chaque row porte son org_id et optionnellement l'ID
  de l'utilisateur créateur.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column


class TimestampMixin:
    """
    Ajoute created_at (immuable) et updated_at (mis à jour automatiquement)
    avec timezone=True sur TOUTES les sous-classes.

    server_default=func.now() garantit que le serveur PostgreSQL renseigne
    la valeur même si l'insert contourne l'ORM (migrations, scripts).
    onupdate=lambda n'est déclenché que par l'ORM — pour les UPDATE SQL
    directs, un trigger PostgreSQL est nécessaire (voir migration 005).
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class OrgScopedMixin:
    org_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
    )


class UserOwnedMixin:
    created_by_user_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
