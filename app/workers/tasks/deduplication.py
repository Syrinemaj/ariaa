"""
Décorateur @deduplicated_task — déduplication des tâches Celery via Redis.

Problème résolu :
  Double-clic sur "Upload HAR" ou double-appel API = deux tâches Celery
  identiques en parallèle → doublons en base + LLM appelé deux fois.

Solution :
  Lock Redis atomique (SET key value NX EX ttl) acquis avant exécution.
  NX = seulement si la clé n'existe pas (atomique, pas de race condition).
  EX = TTL automatique → lock libéré si le worker meurt.

Usage :
    @celery_app.task(bind=True, ...)
    @deduplicated_task(
        key_fn=lambda file_path, org_id, **_: sha256(file_path + org_id),
        timeout_seconds=300,
    )
    def process_har_pipeline(self, file_path, org_id, ...):
        ...
"""
from __future__ import annotations

import hashlib
import logging
from functools import wraps
from typing import Any, Callable

from app.db.redis_client import get_redis

logger = logging.getLogger(__name__)

_LOCK_PREFIX = "task_lock:"


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()[:32]


def deduplicated_task(
    key_fn: Callable[..., str],
    timeout_seconds: int = 300,
):
    """
    Décorateur de déduplication basé sur un lock Redis.

    key_fn(*args, **kwargs) → str
      Doit retourner une clé UNIQUE identifiant cette tâche.
      Appelé avec les arguments de la tâche (self excluded).

    timeout_seconds
      TTL du lock Redis. Choisir : durée max estimée × 1.5.
      Si le worker crash avant la fin, le lock expire automatiquement.

    Comportement :
      - Lock disponible    → acquiert + exécute + libère
      - Lock déjà pris     → log warning + return None (skip silencieux)
      - Exception pendant  → libère le lock + re-raise
    """
    def decorator(task_fn: Callable) -> Callable:
        @wraps(task_fn)
        def wrapper(self, *args, **kwargs) -> Any:
            try:
                lock_key_suffix = key_fn(*args, **kwargs)
            except Exception as exc:
                logger.warning("deduplicated_task: key_fn failed (%s) — running without lock", exc)
                return task_fn(self, *args, **kwargs)

            lock_key = f"{_LOCK_PREFIX}{lock_key_suffix}"
            redis = get_redis()

            # SET key value NX EX ttl — atomic: only sets if key doesn't exist
            acquired = redis.set(lock_key, "1", nx=True, ex=timeout_seconds)

            if not acquired:
                logger.warning(
                    "deduplicated_task: lock '%s' already held — skipping duplicate task",
                    lock_key,
                )
                return None

            try:
                return task_fn(self, *args, **kwargs)
            finally:
                redis.delete(lock_key)

        return wrapper
    return decorator


# ─── Clés de déduplication par type de tâche ─────────────────────────────────

def har_pipeline_key(file_path: str, org_id: str, **_) -> str:
    """Déduplique sur (file_path, org_id) — même fichier, même org."""
    return _sha256(f"har:{file_path}:{org_id}")


def embedding_key(run_id: str, **_) -> str:
    """Un seul job d'embedding par run_id."""
    return f"embed:{run_id}"


def batch_key(job_id: str, batch_number: int, **_) -> str:
    """Un seul job d'exécution par (job_id, batch_number)."""
    return f"batch:{job_id}:{batch_number}"


def report_key(run_id: str, **_) -> str:
    """Un seul rapport par run_id."""
    return f"report:{run_id}"
