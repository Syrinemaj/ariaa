"""
Refresh token lifecycle + JTI blocklist + token versioning.

refresh_token lifecycle (async SQLAlchemy) :
  create_refresh_token()  → INSERT into refresh_tokens (hash SHA-256 only)
  verify_refresh_token()  → SELECT by hash
  rotate_refresh_token()  → revoke old + INSERT new (theft detection)

JTI blocklist (sync Redis) :
  blocklist_jti()         → SETEX sur Redis
  is_jti_blocklisted()    → EXISTS sur Redis

Token version (sync Redis) :
  increment_token_version() → INCR + EXPIRE sur Redis

Le blocklist et le versioning restent sync Redis car ils sont appelés
depuis get_current_user() qui est un dep FastAPI sync-compatible.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.redis_client import get_redis
from app.models.refresh_token import RefreshToken


def _sha256(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _ttl_seconds(expires_at: datetime) -> int:
    delta = expires_at - datetime.now(timezone.utc)
    return max(int(delta.total_seconds()), 0)


# ─── Refresh token lifecycle (async) ─────────────────────────────────────────

async def create_refresh_token(
    db: AsyncSession,
    user_id: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> str:
    """
    Génère un refresh token sécurisé.
    Stocke uniquement le hash SHA-256 en DB — jamais le token brut.
    Retourne le token brut (à transmettre au client une seule fois).
    """
    raw = secrets.token_urlsafe(48)
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    record = RefreshToken(
        user_id=user_id,
        token_hash=_sha256(raw),
        expires_at=expires_at,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(record)
    await db.flush()

    return raw


async def verify_refresh_token(db: AsyncSession, raw: str) -> RefreshToken | None:
    """Recherche un refresh token valide par son hash SHA-256."""
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == _sha256(raw),
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > datetime.now(timezone.utc),
        )
    )
    return result.scalar_one_or_none()


async def rotate_refresh_token(
    db: AsyncSession,
    old_raw: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> tuple[str, str] | None:
    """
    Rotation du refresh token :
      1. Vérifie l'ancien token
      2. Le révoque (revoked_at = now)
      3. Émet un nouveau token

    Détection de vol :
      Si le token est déjà révoqué → quelqu'un essaie de le réutiliser.
      On révoque TOUTE la famille de tokens de cet utilisateur.
      Retourne None dans les deux cas d'échec.
    """
    old_hash = _sha256(old_raw)
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == old_hash)
    )
    record = result.scalar_one_or_none()

    if record is None:
        return None

    if record.revoked_at is not None or record.expires_at <= datetime.now(timezone.utc):
        # Theft detection — revoke all tokens for this user
        await _revoke_all_user_tokens(db, record.user_id)
        await db.flush()
        return None

    record.revoked_at = datetime.now(timezone.utc)
    await db.flush()

    new_raw = await create_refresh_token(
        db=db,
        user_id=record.user_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    return new_raw, record.user_id


async def _revoke_all_user_tokens(db: AsyncSession, user_id: str) -> None:
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(timezone.utc))
    )


# ─── JTI blocklist (sync Redis — rapide, pas de blocage significatif) ─────────

def blocklist_jti(jti: str, expires_at: datetime) -> None:
    """Ajoute un JTI à la blocklist Redis avec TTL = durée restante du token."""
    redis = get_redis()
    ttl = _ttl_seconds(expires_at)
    if ttl > 0:
        redis.setex(f"jti_blocklist:{jti}", ttl, "1")


def is_jti_blocklisted(jti: str) -> bool:
    return get_redis().exists(f"jti_blocklist:{jti}") == 1


# ─── Token versioning (sync Redis) ───────────────────────────────────────────

def increment_token_version(user_id: str) -> int:
    """
    Incrémente la version du token d'un utilisateur dans Redis.
    Tout access token avec une version antérieure est immédiatement rejeté.
    Utilisé lors de : désactivation, changement de rôle, logout forcé.
    """
    redis = get_redis()
    key = f"token_version:{user_id}"
    new_version = redis.incr(key)
    redis.expire(key, settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60 * 2)
    return new_version
