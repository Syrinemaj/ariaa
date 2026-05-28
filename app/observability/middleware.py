import time

from starlette.middleware.base import BaseHTTPMiddleware

from app.observability.metrics import http_request_duration_seconds, http_requests_total


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        started_at = time.time()
        response = await call_next(request)
        duration = time.time() - started_at

        path = request.url.path
        method = request.method
        status = str(response.status_code)

        http_requests_total.labels(method=method, path=path, status=status).inc()
        http_request_duration_seconds.labels(method=method, path=path).observe(duration)

        return response
