from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.approvals import router as approvals_router
from app.api.audit import router as audit_router
from app.api.auth import router as auth_router
from app.api.automation import router as automation_router
from app.api.bulk import router as bulk_router
from app.api.jobs import router as jobs_router
from app.api.maintenance import router as maintenance_router
from app.api.openapi import router as openapi_router
from app.api.rag import router as rag_router
from app.api.registry import router as registry_router
from app.api.reports import router as reports_router
from app.api.upload import router as upload_router
from app.api.users import router as users_router
from app.core.config import settings
from app.core.rate_limit import limiter
from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.observability.metrics import metrics_response
from app.observability.middleware import MetricsMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── AI client singleton ─────────────────────────────────────────────────
    from app.ai.azure_openai_client import AzureOpenAIClient
    app.state.ai_client = AzureOpenAIClient()

    # ── Async Redis pool ────────────────────────────────────────────────────
    pool = aioredis.ConnectionPool.from_url(
        settings.REDIS_APP_URL,
        max_connections=20,
        decode_responses=True,
    )
    app.state.redis = aioredis.Redis(connection_pool=pool)

    # ── Database ────────────────────────────────────────────────────────────
    init_db()

    # ── Observability ───────────────────────────────────────────────────────
    from app.observability.metrics import initialize_metrics
    initialize_metrics(model_name=settings.AZURE_OPENAI_MODEL)

    from app.llm_observability.service import print_current_ai_usage_today
    db = SessionLocal()
    try:
        print_current_ai_usage_today(db)
    finally:
        db.close()

    yield

    await app.state.redis.aclose()


app = FastAPI(title="ARIA", lifespan=lifespan)

# ── /metrics IP guard ────────────────────────────────────────────────────────
_METRICS_ALLOWED_IPS: set[str] = set()


@app.middleware("http")
async def metrics_guard(request: Request, call_next):
    """
    Protège /metrics contre l'accès non autorisé.

    Deux modes (non exclusifs) :
    1. IP whitelist : METRICS_ALLOWED_IPS (comma-separated)
    2. Bearer token : METRICS_BEARER_TOKEN (si non vide)

    Raison : /metrics expose les performances internes, compteurs de requêtes,
    durées d'exécution — informations précieuses pour un attaquant.
    Sans protection, n'importe quelle IP peut les lire.
    """
    if request.url.path == "/metrics":
        # Resolve allowed IPs lazily (settings available at runtime)
        allowed_ips = {
            ip.strip()
            for ip in settings.METRICS_ALLOWED_IPS.split(",")
            if ip.strip()
        }

        client_ip = request.client.host if request.client else ""

        # Check Bearer token first if configured
        if settings.METRICS_BEARER_TOKEN:
            auth = request.headers.get("authorization", "")
            if auth == f"Bearer {settings.METRICS_BEARER_TOKEN}":
                return await call_next(request)

        if client_ip not in allowed_ips:
            return JSONResponse(
                status_code=403,
                content={"detail": "Access to /metrics forbidden from this IP"},
            )

    return await call_next(request)


app.add_middleware(MetricsMiddleware)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

from app.observability.tracing import setup_tracing
setup_tracing(app)

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(upload_router)
app.include_router(registry_router)
app.include_router(openapi_router)
app.include_router(rag_router)
app.include_router(automation_router)
app.include_router(reports_router)
app.include_router(bulk_router)
app.include_router(approvals_router)
app.include_router(audit_router)
app.include_router(maintenance_router)
app.include_router(jobs_router)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/metrics")
async def metrics():
    return metrics_response()
