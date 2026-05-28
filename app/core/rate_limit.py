"""
Rate limiting distribué via Redis — deux limiteurs disponibles.

Problème résolu :
  4 workers uvicorn = 4 compteurs EN MÉMOIRE distincts = limite effective × 4.
  Résultat : 100 req/min configuré → 400 req/min réellement autorisé.

Solution :
  slowapi + Redis backend → un seul compteur partagé entre TOUS les workers.
  Les compteurs sont incrémentés dans Redis atomiquement (INCR + EXPIRE).

Deux clés de rate limiting :

1. limiter (par IP)
   Utilisé pour les endpoints non authentifiés ou peu critiques.
   Clé = adresse IP source.

2. limiter_by_user (par user_id ou IP si non authentifié)
   Utilisé pour les endpoints authentifiés et critiques.
   Clé = "user:{id}" si JWT valide, sinon IP.
   Empêche l'abus multi-IP (VPN rotation, botnets) par le même utilisateur.

Limites par endpoint (appliquées via @limiter.limit() dans les routes) :
  /upload/har/analyze  → 10/hour   (pipeline LLM lourd, coûteux)
  /bulk/execute        → 5/minute  (enqueue massif)
  /auth/login          → 5/minute  (anti brute-force)
  /api/*               → 100/minute (usage normal)
"""
from __future__ import annotations

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings


def get_user_or_ip(request: Request) -> str:
    """
    Rate limit key: user ID extracted from JWT if present, else remote IP.

    Why decode the token here instead of using Depends(get_current_user):
    slowapi's key_func runs BEFORE route dependencies, so the user object
    is not yet available. We do a lightweight JWT decode (no DB query) just
    to extract the sub claim.
    """
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
        try:
            from app.auth.jwt import decode_access_token
            payload = decode_access_token(token)
            user_id = payload.get("sub")
            if user_id:
                return f"user:{user_id}"
        except Exception:
            pass
    return get_remote_address(request)


# ── By IP — for unauthenticated or low-risk endpoints ────────────────────────
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=settings.REDIS_APP_URL,
    strategy="fixed-window",
)

# ── By user_id (or IP fallback) — for authenticated, high-risk endpoints ─────
limiter_by_user = Limiter(
    key_func=get_user_or_ip,
    storage_uri=settings.REDIS_APP_URL,
    strategy="fixed-window",
)
