"""
Prometheus metrics for ARIA.

LLM metrics carry a `provider` label ("azure" | "groq") so Grafana can
build separate dashboards per AI backend without duplicating counter names.

New in this version:
  aria_llm_embedding_fallback_total  — incremented every time GroqClient
    returns a zero vector because Groq has no embedding endpoint. Visible
    in the Groq dashboard as an indicator of degraded RAG quality.
"""
from __future__ import annotations

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from starlette.responses import Response

# ── HTTP layer ────────────────────────────────────────────────────────────────

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

# ── LLM layer (provider label enables per-backend Grafana panels) ─────────────

llm_tokens_total = Counter(
    "aria_llm_tokens_total",
    "Total LLM tokens used",
    ["task_name", "model_name", "provider"],
)

llm_cost_total = Counter(
    "aria_llm_cost_total",
    "Estimated LLM cost USD",
    ["task_name", "model_name", "provider"],
)

# ── Real AWS billed cost (Cost Explorer) ───────────────────────────────────
# Unlike llm_cost_total (only sees calls made through app/llm_observability/),
# this reflects what AWS actually billed for the account, regardless of which
# code path (production API, evaluation scripts, manual boto3 test) caused it.
# Gauge, not Counter — set (not incremented) to the latest Cost Explorer value
# on each sync, since Cost Explorer already returns cumulative period totals.
aws_billed_cost_usd = Gauge(
    "aria_aws_billed_cost_usd",
    "Real AWS cost this month-to-date, from Cost Explorer, by service",
    ["service"],
)

# The generic "Amazon Bedrock" SERVICE bucket lumps every on-demand model
# together (production deepseek.v3.2 alongside every model evaluation/
# run_scripts/* swept) — only Anthropic's marketplace-listed models get
# their own SERVICE name. This breaks that bucket down by USAGE_TYPE
# (parsed to a bare model name) so the production model can be isolated
# from eval-script noise.
aws_bedrock_model_cost_usd = Gauge(
    "aria_aws_bedrock_model_cost_usd",
    "Real AWS cost this month-to-date for on-demand Bedrock usage, by model "
    "(parsed from Cost Explorer USAGE_TYPE, since these don't get their own SERVICE line)",
    ["model"],
)

aws_cost_last_sync_timestamp = Gauge(
    "aria_aws_cost_last_sync_timestamp_seconds",
    "Unix timestamp of the last successful Cost Explorer sync",
)

# Groq has no embedding API — every call returns a zero vector.
# This counter surfaces the impact on RAG quality.
llm_embedding_fallback_total = Counter(
    "aria_llm_embedding_fallback_total",
    "Times a zero-vector was returned instead of a real embedding",
    ["provider"],
)

# ── Bulk execution ────────────────────────────────────────────────────────────

bulk_batches_total = Counter(
    "aria_bulk_batches_total",
    "Total bulk batches processed",
    ["status"],
)

bulk_failed_rows_total = Counter(
    "aria_bulk_failed_rows_total",
    "Total failed bulk rows",
)

# ── Target API ────────────────────────────────────────────────────────────────

target_api_errors_total = Counter(
    "aria_target_api_errors_total",
    "Target API errors by endpoint",
    ["endpoint_key", "status_code"],
)

# ── Uploads ───────────────────────────────────────────────────────────────────

upload_file_size_bytes = Histogram(
    "aria_upload_file_size_bytes",
    "Uploaded file size in bytes",
    ["file_type"],
)

# ── Active runs ───────────────────────────────────────────────────────────────

active_automation_runs = Gauge(
    "aria_active_automation_runs",
    "Currently active automation runs",
)

# ── Ingestion quality ─────────────────────────────────────────────────────────

aria_semantic_filter_fallback_total = Counter(
    "aria_semantic_filter_fallback_total",
    "Ambiguous HAR entries rejected because AI was unavailable during ingestion",
)


# ── Initialisation ────────────────────────────────────────────────────────────

def initialize_metrics(
    model_name: str = "gpt-4o-mini",
    provider: str = "azure",
) -> None:
    """
    Pre-register label combinations so they appear in Prometheus from startup,
    not only after the first LLM call. Call once in the FastAPI lifespan.
    """
    for task in (
        "har_classification",
        "endpoint_understanding",
        "intent_analysis",
        "batch_param_inference",
        "unknown",
    ):
        llm_tokens_total.labels(
            task_name=task, model_name=model_name, provider=provider
        ).inc(0)
        llm_cost_total.labels(
            task_name=task, model_name=model_name, provider=provider
        ).inc(0)

    llm_embedding_fallback_total.labels(provider=provider).inc(0)
    bulk_batches_total.labels(status="completed").inc(0)
    bulk_batches_total.labels(status="failed").inc(0)


# ── Record helpers ────────────────────────────────────────────────────────────

def record_llm_tokens(
    task_name: str,
    model_name: str,
    total_tokens: int,
    estimated_cost: float,
    provider: str = "azure",
) -> None:
    """Increment LLM token and cost counters with provider label."""
    llm_tokens_total.labels(
        task_name=task_name, model_name=model_name, provider=provider
    ).inc(total_tokens)
    llm_cost_total.labels(
        task_name=task_name, model_name=model_name, provider=provider
    ).inc(estimated_cost)


def record_embedding_fallback(provider: str = "groq") -> None:
    """Increment the zero-vector fallback counter (called by GroqClient)."""
    llm_embedding_fallback_total.labels(provider=provider).inc()


def record_bulk_batch(status: str) -> None:
    bulk_batches_total.labels(status=status).inc()


def record_target_api_error(endpoint_key: str, status_code: int | str) -> None:
    target_api_errors_total.labels(
        endpoint_key=endpoint_key,
        status_code=str(status_code),
    ).inc()


def metrics_response() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
