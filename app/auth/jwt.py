from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from jose import JWTError, jwt

from app.core.config import settings


def _get_token_version(user_id: str) -> int:
    """
    Read the token_version for a user from Redis.
    Returns 0 if no version is stored (first token ever issued).
    Used to bulk-invalidate all tokens on role change / deactivation.
    """
    from app.db.redis_client import get_redis
    redis = get_redis()
    raw = redis.get(f"token_version:{user_id}")
    return int(raw) if raw is not None else 0


def create_access_token(
    subject: str,
    email: str,
    role: str,
    org_id: str,
    expires_delta: timedelta | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta
        or timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    payload: dict[str, Any] = {
        "sub": subject,
        "jti": str(uuid4()),
        "email": email,
        "role": role,
        "org_id": org_id,
        "token_version": _get_token_version(subject),
        "iat": int(now.timestamp()),
        "exp": expire,
    }

    return jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except JWTError as error:
        raise ValueError("Invalid or expired token") from error
