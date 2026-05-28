from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

http_requests_total = Counter(
    "aria_http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)

http_request_duration_seconds = Histogram(
    "aria_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path"],
)

llm_tokens_total = Counter(
    "aria_llm_tokens_total",
    "Total LLM tokens used",
    ["task_name", "model_name"],
)

llm_cost_total = Counter(
    "aria_llm_cost_total",
    "Estimated LLM cost USD",
    ["task_name", "model_name"],
)

bulk_batches_total = Counter(
    "aria_bulk_batches_total",
    "Total bulk batches processed",
    ["status"],
)

bulk_failed_rows_total = Counter(
    "aria_bulk_failed_rows_total",
    "Total failed bulk rows",
)

target_api_errors_total = Counter(
    "aria_target_api_errors_total",
    "Target API errors by endpoint",
    ["endpoint_key", "status_code"],
)

upload_file_size_bytes = Histogram(
    "aria_upload_file_size_bytes",
    "Uploaded file size in bytes",
    ["file_type"],
)

active_automation_runs = Gauge(
    "aria_active_automation_runs",
    "Currently active automation runs",
)


def initialize_metrics(model_name: str = "gpt-4o-mini") -> None:
    """Pre-register LLM metric labels so they appear in Prometheus before any LLM call."""
    for task in ("har_classification", "endpoint_understanding", "intent_analysis", "unknown"):
        llm_tokens_total.labels(task_name=task, model_name=model_name).inc(0)
        llm_cost_total.labels(task_name=task, model_name=model_name).inc(0)
    bulk_batches_total.labels(status="completed").inc(0)
    bulk_batches_total.labels(status="failed").inc(0)


def metrics_response() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def record_llm_tokens(task_name: str, model_name: str, total_tokens: int, estimated_cost: float) -> None:
    llm_tokens_total.labels(task_name=task_name, model_name=model_name).inc(total_tokens)
    llm_cost_total.labels(task_name=task_name, model_name=model_name).inc(estimated_cost)


def record_bulk_batch(status: str) -> None:
    bulk_batches_total.labels(status=status).inc()


def record_target_api_error(endpoint_key: str, status_code: int | str) -> None:
    target_api_errors_total.labels(
        endpoint_key=endpoint_key,
        status_code=str(status_code),
    ).inc()
