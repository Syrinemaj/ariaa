"""
Configuration Celery — topologie des queues ARIA.

5 queues séparées avec des workers aux concurrences adaptées :

  ingestion  → 4 workers, concurrency=2  (lent : LLM + IO + CPU)
  embedding  → 2 workers, concurrency=1  (limité Azure OpenAI quotas)
  execution  → 8 workers, concurrency=10 (IO-bound : httpx + PostgreSQL)
  reporting  → 2 workers, concurrency=2  (léger : agrégation SQL)
  maintenance→ 1 worker,  concurrency=1  (basse priorité : cron)

Commandes de démarrage (un process par queue) :
  celery -A app.workers.celery_app worker -Q ingestion  -c 2  --loglevel=info
  celery -A app.workers.celery_app worker -Q embedding  -c 1  --loglevel=info
  celery -A app.workers.celery_app worker -Q execution  -c 10 --loglevel=info
  celery -A app.workers.celery_app worker -Q reporting  -c 2  --loglevel=info
  celery -A app.workers.celery_app worker -Q maintenance -c 1 --loglevel=info
  celery -A app.workers.celery_app beat   --loglevel=info
"""
from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "aria",
    broker=settings.REDIS_BROKER_URL,
    backend=settings.REDIS_BACKEND_URL,
    include=[
        "app.workers.test_task",
        "app.workers.tasks.ingestion",
        "app.workers.tasks.embedding",
        "app.workers.tasks.execution",
        "app.workers.tasks.cleanup",
        "app.workers.tasks.reporting",
    ],
)

celery_app.conf.update(
    # ── Reliability ─────────────────────────────────────────────────────────
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,

    # ── Expiry ──────────────────────────────────────────────────────────────
    result_expires=3600,
    result_backend_transport_options={"retry_on_timeout": True},

    # ── Broker ──────────────────────────────────────────────────────────────
    broker_connection_retry_on_startup=True,
    broker_transport_options={"visibility_timeout": 3600},

    # ── Serialization ───────────────────────────────────────────────────────
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # ── Queue routing ────────────────────────────────────────────────────────
    task_routes={
        "aria.tasks.ingestion.*": {"queue": "ingestion"},
        "aria.tasks.embedding.*": {"queue": "embedding"},
        "aria.tasks.execution.*": {"queue": "execution"},
        "aria.tasks.reporting.*": {"queue": "reporting"},
        "aria.tasks.cleanup.*":   {"queue": "maintenance"},
    },

    # ── Celery Beat — tâches planifiées ──────────────────────────────────────
    beat_schedule={
        # Nettoyage des fichiers HAR toutes les nuits à 2h UTC
        "cleanup-expired-files-daily": {
            "task": "aria.tasks.cleanup.cleanup_expired_files",
            "schedule": crontab(hour=2, minute=0),
            "options": {"queue": "maintenance"},
        },
    },
)
