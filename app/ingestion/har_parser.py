"""
HAR file parser — converts raw HAR JSON into TrafficEntry objects.

Fix 12.2: query parameters are now extracted from the URL and stored in
TrafficEntry.query_params. Previously only path was kept, causing
GET /reports?type=monthly and GET /reports?type=annual to be treated as
identical endpoints.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from app.ingestion.models import TrafficEntry


def _headers_to_dict(headers: List[Dict[str, str]]) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for header in headers or []:
        name = header.get("name")
        value = header.get("value")
        if name:
            result[name.lower()] = value or ""
    return result


def _safe_json_loads(value: Optional[str]) -> Optional[Any]:
    if not value:
        return None
    try:
        return json.loads(value)
    except Exception:
        return value


def _extract_request_body(request: Dict[str, Any]) -> Optional[Any]:
    post_data = request.get("postData")
    if not post_data:
        return None
    return _safe_json_loads(post_data.get("text"))


def _extract_response_body(response: Dict[str, Any]) -> Optional[Any]:
    text = response.get("content", {}).get("text")
    return _safe_json_loads(text)


def _extract_mime_type(response: Dict[str, Any]) -> Optional[str]:
    mime_type = response.get("content", {}).get("mimeType")
    return mime_type.lower() if mime_type else None


def _extract_query_params(query_string: str) -> Dict[str, str]:
    """
    Parse a URL query string into a flat {name: first_value} dict.

    Uses the first observed value per key; HAR entries represent single
    HTTP calls so multi-value params are rare and the first value suffices
    for endpoint fingerprinting.
    """
    if not query_string:
        return {}
    parsed = parse_qs(query_string, keep_blank_values=True)
    return {k: v[0] for k, v in parsed.items() if v}


def parse_har_file(file_path: str | Path) -> List[TrafficEntry]:
    """Parse a HAR file and return one TrafficEntry per HTTP entry."""
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"HAR file not found: {file_path}")

    with path.open("r", encoding="utf-8") as f:
        har_data = json.load(f)

    entries = har_data.get("log", {}).get("entries", [])
    traffic_entries: List[TrafficEntry] = []

    for entry in entries:
        request = entry.get("request", {})
        response = entry.get("response", {})

        method = request.get("method", "").upper()
        url = request.get("url", "")

        if not method or not url:
            continue

        parsed_url = urlparse(url)

        traffic_entries.append(TrafficEntry(
            method=method,
            url=url,
            path=parsed_url.path or "/",
            query_params=_extract_query_params(parsed_url.query),
            status=response.get("status"),
            mime_type=_extract_mime_type(response),
            request_headers=_headers_to_dict(request.get("headers", [])),
            response_headers=_headers_to_dict(response.get("headers", [])),
            request_body=_extract_request_body(request),
            response_body=_extract_response_body(response),
        ))

    return traffic_entries
