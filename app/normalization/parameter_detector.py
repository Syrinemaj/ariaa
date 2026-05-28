from typing import Any, Optional

from app.normalization.patterns import (
    CONTRACT_ID_PATTERN,
    CUSTOMER_ID_PATTERN,
    DATE_PATTERN,
    DATETIME_PATTERN,
    EMPLOYEE_ID_PATTERN,
    GENERIC_BUSINESS_ID_PATTERN,
    HASH_PATTERN,
    INVOICE_ID_PATTERN,
    JWT_PATTERN,
    NUMERIC_ID_PATTERN,
    ORDER_ID_PATTERN,
    PAYMENT_ID_PATTERN,
    UUID_PATTERN,
)
from app.normalization.payload_analyzer import find_parameter_name_from_payload


RESOURCE_PARAMETER_NAMES = {
    "users": "user_id",
    "user": "user_id",
    "employees": "employee_id",
    "employee": "employee_id",
    "customers": "customer_id",
    "customer": "customer_id",
    "orders": "order_id",
    "order": "order_id",
    "invoices": "invoice_id",
    "invoice": "invoice_id",
    "payments": "payment_id",
    "payment": "payment_id",
    "contracts": "contract_id",
    "contract": "contract_id",
    "departments": "department_id",
    "department": "department_id",
    "products": "product_id",
    "product": "product_id",
    "tickets": "ticket_id",
    "ticket": "ticket_id",
    "documents": "document_id",
    "document": "document_id",
    "files": "file_id",
    "file": "file_id",
}


def detect_parameter_type(segment: str) -> Optional[str]:
    if not segment:
        return None

    if NUMERIC_ID_PATTERN.match(segment):
        return "integer"
    if UUID_PATTERN.match(segment):
        return "uuid"
    if JWT_PATTERN.match(segment):
        return "token"
    if DATE_PATTERN.match(segment):
        return "date"
    if DATETIME_PATTERN.match(segment):
        return "datetime"
    if INVOICE_ID_PATTERN.match(segment):
        return "invoice_id"
    if PAYMENT_ID_PATTERN.match(segment):
        return "payment_id"
    if EMPLOYEE_ID_PATTERN.match(segment):
        return "employee_id"
    if ORDER_ID_PATTERN.match(segment):
        return "order_id"
    if CUSTOMER_ID_PATTERN.match(segment):
        return "customer_id"
    if CONTRACT_ID_PATTERN.match(segment):
        return "contract_id"
    if HASH_PATTERN.match(segment):
        return "hash"
    if GENERIC_BUSINESS_ID_PATTERN.match(segment):
        return "business_id"

    return None


def _singularize(resource: str) -> str:
    resource = resource.lower().strip()
    if resource.endswith("ies"):
        return resource[:-3] + "y"
    if resource.endswith("s"):
        return resource[:-1]
    return resource


def infer_parameter_name(
    previous_segment: Optional[str],
    detected_type: str,
    raw_value: str,
    request_body: Any = None,
    response_body: Any = None,
) -> tuple[str, str, float]:
    payload_name = find_parameter_name_from_payload(
        raw_value=raw_value,
        request_body=request_body,
        response_body=response_body,
    )
    if payload_name:
        return payload_name, "payload", 0.95

    if detected_type in {"invoice_id", "payment_id", "employee_id", "order_id", "customer_id", "contract_id"}:
        return detected_type, "rules", 0.95

    if previous_segment:
        normalized_previous = previous_segment.lower().strip()
        if normalized_previous in RESOURCE_PARAMETER_NAMES:
            return RESOURCE_PARAMETER_NAMES[normalized_previous], "context_rules", 0.90
        singular = _singularize(normalized_previous)
        if singular:
            return f"{singular}_id", "context_rules", 0.80

    if detected_type == "uuid":
        return "uuid", "rules", 0.75
    if detected_type == "token":
        return "token", "rules", 0.90
    if detected_type == "date":
        return "date", "rules", 0.90
    if detected_type == "datetime":
        return "datetime", "rules", 0.90
    if detected_type == "hash":
        return "hash", "rules", 0.70
    if detected_type == "business_id":
        return "business_id", "rules_ambiguous", 0.50

    return "id", "fallback", 0.40
