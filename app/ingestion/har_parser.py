import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from app.ingestion.models import TrafficEntry


def _headers_to_dict(headers: List[Dict[str, str]]) -> Dict[str, str]:
    result = {}
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


def parse_har_file(file_path: str | Path) -> List[TrafficEntry]:
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
            status=response.get("status"),
            mime_type=_extract_mime_type(response),
            request_headers=_headers_to_dict(request.get("headers", [])),
            response_headers=_headers_to_dict(response.get("headers", [])),
            request_body=_extract_request_body(request),
            response_body=_extract_response_body(response),
        ))

    return traffic_entries
