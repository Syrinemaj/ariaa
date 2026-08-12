"""
Real AWS billed cost sync — Cost Explorer → Prometheus.

aria_llm_cost_total only sees calls made through app/llm_observability/
(production API traffic). It does not see evaluation/run_scripts/* sweeps,
which call Bedrock directly via boto3 and are intentionally excluded from
app/ instrumentation (see evaluation/tracer/normalization_tracer.py). That
gap is invisible in Grafana unless something reads the real AWS bill.

This queries Cost Explorer's GetCostAndUsage (month-to-date) two ways:

  1. Grouped by SERVICE — Anthropic's marketplace-listed Bedrock models each
     bill under their own service name (e.g. "Claude Sonnet 4.6 (Amazon
     Bedrock Edition)"), so grouping by SERVICE already isolates those.

  2. Grouped by USAGE_TYPE, filtered to SERVICE="Amazon Bedrock" — every
     *non*-marketplace on-demand model (deepseek.v3.2, the Nova/Llama/Qwen/
     etc. models evaluation/run_scripts/* also sweeps) lands in that ONE
     generic "Amazon Bedrock" service line with no per-model breakdown.
     USAGE_TYPE strings look like "EUW2-deepseek.v3.2-mantle-input-tokens-
     standard" — stripping the region prefix and token-count suffix leaves
     the bare model name, which is the only way to isolate BEDROCK_MODEL's
     (production model) real cost from every other model swept in eval runs.

Runs as a background asyncio task from the FastAPI lifespan (see main.py) —
single-process, same one Prometheus scrapes for /metrics, so no multiprocess
registry or pushgateway needed. Cost Explorer itself bills $0.01/request and
has ~24h data lag, so this polls on a multi-hour interval
(AWS_COST_SYNC_INTERVAL_SECONDS), never on every request.
"""
from __future__ import annotations

import asyncio
import re
from datetime import date, timedelta

from app.core.config import settings
from app.core.logging import get_logger
from app.observability.metrics import (
    aws_bedrock_model_cost_usd,
    aws_billed_cost_usd,
    aws_cost_last_sync_timestamp,
)

logger = get_logger(__name__)

_REGION_PREFIX_RE = re.compile(r"^[A-Z]{2,4}\d?-")
_TOKEN_SUFFIX_RE = re.compile(r"-(mantle-)?(input|output)-tokens(-standard)?$")


def _model_name_from_usage_type(usage_type: str) -> str:
    """'EUW2-deepseek.v3.2-mantle-input-tokens-standard' -> 'deepseek.v3.2'."""
    name = _REGION_PREFIX_RE.sub("", usage_type)
    name = _TOKEN_SUFFIX_RE.sub("", name)
    return name or usage_type


def _fetch_month_to_date_costs() -> tuple[dict[str, float], dict[str, float]]:
    """Sync boto3 calls — run via asyncio.to_thread, never on the event loop.
    Returns (cost_by_service, cost_by_bedrock_model)."""
    import boto3

    ce = boto3.client("ce", region_name="us-east-1")  # Cost Explorer is a global/us-east-1 API
    end = date.today() + timedelta(days=1)
    start = date(end.year, end.month, 1)
    period = {"Start": start.isoformat(), "End": end.isoformat()}

    by_service_resp = ce.get_cost_and_usage(
        TimePeriod=period,
        Granularity="MONTHLY",
        Metrics=["UnblendedCost"],
        GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
    )
    cost_by_service: dict[str, float] = {}
    for result in by_service_resp["ResultsByTime"]:
        for group in result["Groups"]:
            service = group["Keys"][0]
            amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
            cost_by_service[service] = cost_by_service.get(service, 0.0) + amount

    by_usage_resp = ce.get_cost_and_usage(
        TimePeriod=period,
        Granularity="MONTHLY",
        Metrics=["UnblendedCost"],
        Filter={"Dimensions": {"Key": "SERVICE", "Values": ["Amazon Bedrock"]}},
        GroupBy=[{"Type": "DIMENSION", "Key": "USAGE_TYPE"}],
    )
    cost_by_model: dict[str, float] = {}
    for result in by_usage_resp["ResultsByTime"]:
        for group in result["Groups"]:
            model = _model_name_from_usage_type(group["Keys"][0])
            amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
            cost_by_model[model] = cost_by_model.get(model, 0.0) + amount

    return cost_by_service, cost_by_model


async def sync_aws_cost_metrics() -> None:
    """Fetch real month-to-date AWS cost and update the Gauges. Never raises —
    a missing/invalid credential or missing ce:GetCostAndUsage permission
    should degrade to 'stale metric', not crash the sync loop or startup."""
    try:
        cost_by_service, cost_by_model = await asyncio.to_thread(_fetch_month_to_date_costs)
    except Exception as exc:
        logger.warning("aws_cost_sync.failed", error=str(exc))
        return

    for service, amount in cost_by_service.items():
        aws_billed_cost_usd.labels(service=service).set(amount)
    for model, amount in cost_by_model.items():
        aws_bedrock_model_cost_usd.labels(model=model).set(amount)
    aws_cost_last_sync_timestamp.set_to_current_time()

    logger.info(
        "aws_cost_sync.updated",
        services=len(cost_by_service),
        bedrock_models=len(cost_by_model),
        total_usd=round(sum(cost_by_service.values()), 4),
        production_model=settings.BEDROCK_MODEL,
        production_model_cost_usd=round(cost_by_model.get(settings.BEDROCK_MODEL, 0.0), 4),
    )


async def run_aws_cost_sync_loop() -> None:
    """Background loop started once from the FastAPI lifespan. Syncs
    immediately on startup, then every AWS_COST_SYNC_INTERVAL_SECONDS."""
    if not settings.AWS_COST_SYNC_ENABLED:
        return
    while True:
        await sync_aws_cost_metrics()
        await asyncio.sleep(settings.AWS_COST_SYNC_INTERVAL_SECONDS)
