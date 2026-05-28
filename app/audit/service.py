"""
Audit service — async SQLAlchemy + sanitisation complète.

sanitize_audit_metadata() protège contre la fuite de données sensibles
dans les logs d'audit. Elle est appliquée :
  1. Sur tous les metadata passés à log_audit_event()
  2. Sur request_payload dans AutomationStepLog (via sanitize_payload())

Clés sensibles :
  authorization, bearer, token, access_token, refresh_token
  password, secret, client_secret, api_key, x_api_key
  auth_headers (clé complète, pas juste les sous-clés)
  cookie, session

La sanitisation est récursive (dict imbriqués) et insensible à la casse.
"""
from __future__ import annotations

import json

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.user import User

# Fragments de noms de clés à masquer (comparaison par sous-chaîne, insensible à la casse)
_SENSITIVE_FRAGMENTS = frozenset({
    "authorization", "bearer", "token", "access_token", "refresh_token",
    "password", "secret", "client_secret", "api_key", "x_api_key",
    "auth_headers", "auth_header", "cookie", "session",
})

_REDACTED = "***REDACTED***"


def sanitize_audit_metadata(value) -> object:
    """
    Sanitise récursivement un objet en masquant les champs sensibles.
    Utiliser sur TOUT metadata avant de l'écrire dans un log ou audit event.
    """
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            normalized = str(key).lower().replace("-", "_").replace(" ", "_")
            if any(fragment in normalized for fragment in _SENSITIVE_FRAGMENTS):
                sanitized[key] = _REDACTED
            else:
                sanitized[key] = sanitize_audit_metadata(item)
        return sanitized
    if isinstance(value, list):
        return [sanitize_audit_metadata(item) for item in value]
    return value


def sanitize_payload(payload) -> dict:
    """
    Sanitise un request_payload HTTP avant stockage dans AutomationStepLog.
    Masque authorization headers, bearer tokens, credentials.
    """
    if not isinstance(payload, dict):
        return {"_sanitized": True, "_type": type(payload).__name__}
    return sanitize_audit_metadata(payload)


async def log_audit_event(
    db: AsyncSession,
    user: User,
    action: str,
    resource_type: str | None = None,
    resource_id: str | None = None,
    metadata: dict | None = None,
) -> AuditLog:
    audit_log = AuditLog(
        org_id=user.org_id,
        user_id=user.id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        metadata_json=sanitize_audit_metadata(metadata or {}),
    )

    db.add(audit_log)
    await db.flush()

    return audit_log


async def list_audit_logs(
    db: AsyncSession,
    user: User,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    base_q = (
        select(AuditLog)
        .where(AuditLog.org_id == user.org_id)
        .order_by(AuditLog.created_at.desc())
    )

    count_result = await db.execute(
        select(func.count()).select_from(
            select(AuditLog.id).where(AuditLog.org_id == user.org_id).subquery()
        )
    )
    total = count_result.scalar_one()

    result = await db.execute(base_q.offset((page - 1) * page_size).limit(page_size))
    logs = result.scalars().all()

    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": max(1, (total + page_size - 1) // page_size),
        "logs": [
            {
                "id": log.id,
                "action": log.action,
                "resource_type": log.resource_type,
                "resource_id": log.resource_id,
                "user_id": log.user_id,
                "metadata": log.metadata_json,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ],
    }
