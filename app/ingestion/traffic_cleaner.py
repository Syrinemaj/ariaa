from typing import List
from urllib.parse import urlparse

from app.ingestion.models import TrafficEntry


STATIC_EXTENSIONS = {
    ".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
    ".woff", ".woff2", ".ttf", ".map", ".webp", ".mp4", ".mp3",
}

NOISE_DOMAINS = {
    "google-analytics", "googletagmanager", "doubleclick", "hotjar",
    "mixpanel", "segment", "facebook", "sentry", "datadog", "newrelic",
}

API_HINTS = {"/api/", "/graphql", "/rest/", "/v1/", "/v2/", "/v3/"}

BUSINESS_KEYWORDS = {
    "employee", "employees", "user", "users", "customer", "customers",
    "order", "orders", "invoice", "invoices", "payment", "payments",
    "contract", "contracts", "department", "departments", "hire",
    "hiring", "onboarding",
}


def _has_static_extension(path: str) -> bool:
    lower_path = path.lower()
    return any(lower_path.endswith(ext) for ext in STATIC_EXTENSIONS)


def _is_noise_domain(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return any(domain in host for domain in NOISE_DOMAINS)


def _is_static_mime(mime_type: str | None) -> bool:
    if not mime_type:
        return False
    mime_type = mime_type.lower()
    return (
        mime_type.startswith("image/")
        or mime_type.startswith("font/")
        or mime_type in {"text/css", "application/javascript", "text/javascript"}
    )


def _has_json_content(entry: TrafficEntry) -> bool:
    content_type = entry.response_headers.get("content-type", "")
    request_content_type = entry.request_headers.get("content-type", "")
    return (
        "application/json" in content_type
        or "application/json" in request_content_type
        or entry.mime_type == "application/json"
        or isinstance(entry.request_body, (dict, list))
        or isinstance(entry.response_body, (dict, list))
    )


def _has_api_hint(path: str) -> bool:
    lower_path = path.lower()
    return any(hint in lower_path for hint in API_HINTS)


def _has_business_keyword(entry: TrafficEntry) -> bool:
    text = f"{entry.path} {entry.request_body} {entry.response_body}".lower()
    return any(keyword in text for keyword in BUSINESS_KEYWORDS)


def compute_relevance_score(entry: TrafficEntry) -> tuple[float, str]:
    score = 0.0
    reasons = []

    if entry.method in {"POST", "PUT", "PATCH", "DELETE"}:
        score += 0.25
        reasons.append("mutating_http_method")

    if _has_json_content(entry):
        score += 0.35
        reasons.append("json_content")

    if _has_api_hint(entry.path):
        score += 0.25
        reasons.append("api_path_hint")

    if _has_business_keyword(entry):
        score += 0.25
        reasons.append("business_keyword")

    if entry.status and 200 <= entry.status < 400:
        score += 0.10
        reasons.append("successful_status")

    return min(score, 1.0), ",".join(reasons)


def clean_traffic(entries: List[TrafficEntry], min_score: float = 0.35) -> List[TrafficEntry]:
    cleaned: List[TrafficEntry] = []

    for entry in entries:
        if _has_static_extension(entry.path):
            continue
        if _is_noise_domain(entry.url):
            continue
        if _is_static_mime(entry.mime_type):
            continue

        score, reason = compute_relevance_score(entry)
        entry.relevance_score = score
        entry.reason = reason
        entry.is_api_candidate = score >= min_score

        if entry.is_api_candidate:
            cleaned.append(entry)

    return cleaned
