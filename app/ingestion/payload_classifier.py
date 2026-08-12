from typing import Any

from app.ingestion.models import TrafficEntry


BUSINESS_KEYWORDS = {
    "employee", "employees", "user", "users", "customer", "customers",
    "order", "orders", "invoice", "invoices", "payment", "payments",
    "contract", "contracts", "department", "departments", "salary",
    "hire", "hiring", "onboarding", "cart", "checkout", "product", "products",
    "absence", "absences", "conge", "conges", "dossier", "dossiers",
    "matricule", "paie", "effectif", "effectifs", "collaborateur",
    "collaborateurs", "rh", "poste", "workflow", "indicator", "indicateur",
}


def _flatten_payload(payload: Any) -> str:
    if payload is None:
        return ""
    if isinstance(payload, dict):
        parts = []
        for key, value in payload.items():
            parts.append(str(key))
            parts.append(_flatten_payload(value))
        return " ".join(parts)
    if isinstance(payload, list):
        return " ".join(_flatten_payload(item) for item in payload)
    return str(payload)


def compute_payload_score(entry: TrafficEntry) -> float:
    text = " ".join([
        entry.path,
        _flatten_payload(entry.request_body),
        _flatten_payload(entry.response_body),
    ]).lower()

    matched_keywords = [kw for kw in BUSINESS_KEYWORDS if kw in text]

    if not matched_keywords:
        return 0.0

    return min(len(matched_keywords) * 0.12, 0.45)
