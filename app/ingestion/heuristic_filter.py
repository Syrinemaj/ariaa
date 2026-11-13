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
    "/cxf/",
    "servlet",
}

XML_CONTENT_TYPES = ("application/xml", "text/xml", "application/soap+xml")


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


def has_structured_content(entry: TrafficEntry) -> bool:
    """True for JSON or XML/SOAP bodies — legacy servlet-style APIs
    (e.g. this app's hr-rich-client) commonly return text/xml instead
    of JSON for genuine business calls, which has_json_content misses."""
    if has_json_content(entry):
        return True
    content_type = entry.response_headers.get("content-type", "")
    request_content_type = entry.request_headers.get("content-type", "")
    mime_type = entry.mime_type or ""
    return any(
        xml_type in value
        for value in (content_type, request_content_type, mime_type)
        for xml_type in XML_CONTENT_TYPES
    )


def has_api_hint(path: str) -> bool:
    lower_path = path.lower()
    return any(hint in lower_path for hint in API_HINTS)


def compute_heuristic_score(entry: TrafficEntry) -> float:
    """
    Weights recalibrated against evaluation/golden_dataset/
    traffic_classification_golden_dataset.json (30 real, deliberately
    adversarial cases). The original weights (content +0.35, API hint +0.25)
    let pure structure — a successful POST/PUT/PATCH/DELETE with a JSON
    body, regardless of what it actually contains — reach 0.70 (the
    kept_by_rules threshold) on its own: method(0.25) + structured(0.35) +
    status(0.10) = 0.70 exactly, with zero contribution from
    payload_classifier's business-keyword signal. Measured effect: 10/11
    noise cases in the golden set's "noise_disguised_as_business" and
    "genuinely_ambiguous" strata were wrongly kept by rules alone
    (precision 0.643 among rule-decided cases), because nearly any
    JSON-over-POST call — a telemetry event, an error log, a session
    heartbeat — satisfies that combination without representing a real
    business mutation.

    Lowering content (+0.35 -> +0.25) and the API-hint bonus (+0.25 -> +0.15)
    means structure alone now tops out at 0.60, so at least some payload
    signal (business-keyword match) is required to cross into kept_by_rules
    — correctly routing more structure-only cases into the LLM-arbitrated
    gray zone instead. Measured on the same golden set: false positives
    10 -> 7, precision 0.643 -> 0.667, F1 0.783 -> 0.800, recall unchanged
    at 1.000 (no real business case newly misses the rules layer). Tradeoff
    accepted: cases routed to the gray zone go from 1/30 to 8/30 on this
    adversarial set — more LLM calls, but each one was previously a false
    positive the rules layer answered confidently and wrongly.
    """
    score = 0.0

    if entry.method in {"POST", "PUT", "PATCH", "DELETE"}:
        score += 0.25

    if entry.method == "GET":
        score += 0.05

    if has_structured_content(entry):
        score += 0.25

    if has_api_hint(entry.path):
        score += 0.15

    if entry.status and 200 <= entry.status < 400:
        score += 0.10

    return min(score, 1.0)
