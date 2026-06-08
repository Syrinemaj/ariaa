"""
OpenTelemetry setup — OTLP traces with auto-instrumentation.

Instruments:
- FastAPI request/response spans (FastAPIInstrumentor)
- SQLAlchemy queries (SQLAlchemyInstrumentor)
- HTTPX outbound calls (HTTPXClientInstrumentor)

Call setup_telemetry(app) in the FastAPI lifespan hook, after the app object
is created and before the first request is served.

OTEL_ENABLED=false (in .env) disables all instrumentation with zero overhead.
"""
from __future__ import annotations

from fastapi import FastAPI

from app.core.config import settings


def setup_telemetry(app: FastAPI) -> None:
    """Configure OTLP tracing if OTEL_ENABLED is True."""
    if not settings.OTEL_ENABLED:
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        from app.db.session import engine

        resource = Resource.create({"service.name": settings.OTEL_SERVICE_NAME})
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(
            endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT,
            insecure=True,
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        FastAPIInstrumentor.instrument_app(app)
        SQLAlchemyInstrumentor().instrument(engine=engine)
        HTTPXClientInstrumentor().instrument()

    except ImportError:
        import logging
        logging.getLogger(__name__).warning(
            "OpenTelemetry packages not installed — tracing disabled. "
            "Install opentelemetry-sdk opentelemetry-exporter-otlp-proto-grpc "
            "opentelemetry-instrumentation-fastapi opentelemetry-instrumentation-sqlalchemy "
            "opentelemetry-instrumentation-httpx to enable."
        )
