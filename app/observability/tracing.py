from app.core.config import settings


def setup_tracing(app) -> None:
    if not settings.OTEL_ENABLED:
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
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

    except ImportError:
        import logging
        logging.getLogger(__name__).warning(
            "OpenTelemetry packages not installed — tracing disabled. "
            "Install opentelemetry-* packages to enable."
        )
