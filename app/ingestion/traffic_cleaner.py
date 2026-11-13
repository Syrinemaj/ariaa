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
    "analytics.google", "collect.google", "stats.g.doubleclick",
}

NOISE_METHODS = {"OPTIONS", "HEAD"}

NOISE_PATHS = {
    "/health", "/healthz", "/ready", "/readyz", "/ping", "/favicon.ico",
    "/__webpack_hmr", "/__webpack_dev_server__",
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


def clean_traffic(entries: List[TrafficEntry]) -> List[TrafficEntry]:
    """
    Hard filter — removes entries that are definitively not API calls:
    static assets (by extension or MIME type) and known analytics/tracking
    domains.

    Scoring and AI-based classification are handled exclusively by
    noise_scoring.score_entries(), called after this step.
    """
    cleaned: List[TrafficEntry] = []
    for entry in entries:
        if _has_static_extension(entry.path):
            continue
        if _is_noise_domain(entry.url):
            continue
        if _is_static_mime(entry.mime_type):
            continue
        if entry.method in NOISE_METHODS:
            continue
        if entry.path.rstrip("/") in NOISE_PATHS:
            continue
        # HAR convention: status 0 means the browser never got a response
        # (cancelled/aborted/blocked request) — not a real 4xx/5xx from the
        # server. No headers, no body, no status code worth recording; if
        # the same call also succeeded elsewhere in the capture (the usual
        # case — a duplicate fired by the page, then cancelled), dropping
        # this one avoids it contaminating that endpoint's merged status_codes.
        if entry.status == 0:
            continue
        cleaned.append(entry)
    return cleaned
