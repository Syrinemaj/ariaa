from app.ingestion.models import TrafficEntry


API_HINTS = {
    "/api/",
    "/graphql",
    "/rest/",
    "/v1/",
    "/v2/",
    "/v3/",
    "/backend/",
    "/services/",
}


def has_json_content(entry: TrafficEntry) -> bool:
    content_type = entry.response_headers.get("content-type", "")
    request_content_type = entry.request_headers.get("content-type", "")
    return (
        "application/json" in content_type
        or "application/json" in request_content_type
        or entry.mime_type == "application/json"
        or isinstance(entry.request_body, (dict, list))
        or isinstance(entry.response_body, (dict, list))
    )


def has_api_hint(path: str) -> bool:
    lower_path = path.lower()
    return any(hint in lower_path for hint in API_HINTS)


def compute_heuristic_score(entry: TrafficEntry) -> float:
    score = 0.0

    if entry.method in {"POST", "PUT", "PATCH", "DELETE"}:
        score += 0.25

    if entry.method == "GET":
        score += 0.05

    if has_json_content(entry):
        score += 0.35

    if has_api_hint(entry.path):
        score += 0.25

    if entry.status and 200 <= entry.status < 400:
        score += 0.10

    return min(score, 1.0)
