"""
ARIA FastAPI application entry point.

Fix 14.1: setup_telemetry() wires FastAPI + SQLAlchemy + HTTPX into OTLP.
Fix 14.2: add_request_id middleware stamps every request with X-Request-ID
          and stores it in the current_request_id ContextVar so all downstream
          code (logs, LLM calls, Celery tasks) can reference the same trace.
Fix 14.3: setup_logging() configures structlog JSON output before first log.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import uuid4

import redis.asyncio as aioredis
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.approvals import router as approvals_router
from app.api.llm import router as llm_router
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
from app.core.context import current_request_id
from app.core.logging import get_logger, setup_logging
from app.core.rate_limit import limiter
from app.core.telemetry import setup_telemetry
from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.observability.metrics import metrics_response
from app.observability.middleware import MetricsMiddleware

# ── Logging must be configured before the first log emission ────────────────
setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── AI completion client (Groq primary, Azure legacy) ───────────────────
    if settings.AI_PROVIDER == "azure":
        from app.ai.azure_openai_client import AzureOpenAIClient
        app.state.ai_client = AzureOpenAIClient()
        logger.info("ai.provider.selected", provider="azure", model=settings.AZURE_OPENAI_MODEL)
    else:
        from app.ai.groq_client import GroqClient
        app.state.ai_client = GroqClient()
        logger.info("ai.provider.selected", provider="groq", model=settings.GROQ_MODEL)

    # ── Embedding client (always local sentence-transformers) ────────────────
    # Loaded lazily on first call — no startup latency penalty.
    from app.ai.local_embedding_client import LocalEmbeddingClient
    app.state.embedding_client = LocalEmbeddingClient()
    logger.info(
        "ai.embedding.selected",
        provider="local",
        model=settings.LOCAL_EMBEDDING_MODEL,
        dimensions=settings.EMBEDDING_DIMENSIONS,
    )

    # ── Async Redis pool ────────────────────────────────────────────────────
    pool = aioredis.ConnectionPool.from_url(
        settings.REDIS_APP_URL,
        max_connections=20,
        decode_responses=True,
    )
    app.state.redis = aioredis.Redis(connection_pool=pool)

    # ── Database ────────────────────────────────────────────────────────────
    init_db()

    # ── Prometheus metrics ──────────────────────────────────────────────────
    from app.observability.metrics import initialize_metrics
    _metric_model = (
        settings.GROQ_MODEL
        if settings.AI_PROVIDER == "groq"
        else settings.AZURE_OPENAI_MODEL
    )
    initialize_metrics(model_name=_metric_model, provider=settings.AI_PROVIDER)

    # ── Startup AI usage summary ────────────────────────────────────────────
    from app.llm_observability.service import print_current_ai_usage_today
    db = SessionLocal()
    try:
        print_current_ai_usage_today(db)
    finally:
        db.close()

    logger.info("aria.startup", otel_enabled=settings.OTEL_ENABLED)

    yield

    await app.state.redis.aclose()
    logger.info("aria.shutdown")


app = FastAPI(title="ARIA", lifespan=lifespan)

# Must run before any middleware is added (instrument_app calls add_middleware).
setup_telemetry(app)

# ── Middleware stack (outermost → innermost) ──────────────────────────────────

@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """
    Stamp every request with a correlation ID.

    Reads X-Request-ID from the incoming headers; generates a UUID if absent.
    Stores the ID in request.state and in the current_request_id ContextVar
    so it propagates automatically through all async code in this request.
    Echoes the ID back in the response header so clients can correlate retries.
    """
    request_id = request.headers.get("X-Request-ID", str(uuid4()))
    request.state.request_id = request_id
    current_request_id.set(request_id)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


_METRICS_ALLOWED_IPS: set[str] = set()


@app.middleware("http")
async def metrics_guard(request: Request, call_next):
    """
    Protect /metrics against unauthorised access.

    Mode 1 (token): Bearer token in Authorization header.
    Mode 2 (IP):    METRICS_ALLOWED_IPS comma-separated whitelist.

    Without protection, /metrics leaks internal performance counters.
    """
    if request.url.path == "/metrics":
        allowed_ips = {
            ip.strip()
            for ip in settings.METRICS_ALLOWED_IPS.split(",")
            if ip.strip()
        }
        client_ip = request.client.host if request.client else ""

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
app.include_router(llm_router)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/metrics")
async def metrics():
    return metrics_response()
