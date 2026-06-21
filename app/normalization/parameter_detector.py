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
    PREFIXED_RESOURCE_ID_PATTERN,
    UUID_PATTERN,
)
from app.normalization.payload_analyzer import find_parameter_name_from_payload

# Maps the first underscore-segment of a prefixed ID to a parameter name.
# e.g. "emp_soph_001" → prefix "emp" → "employee_id"
_PREFIX_TO_PARAM: dict[str, tuple[str, float]] = {
    "emp":          ("employee_id",   0.88),
    "employee":     ("employee_id",   0.88),
    "ctr":          ("contract_id",   0.88),
    "cont":         ("contract_id",   0.88),
    "contract":     ("contract_id",   0.88),
    "pay":          ("payment_id",    0.85),
    "payment":      ("payment_id",    0.85),
    "payroll":      ("payroll_id",    0.85),
    "ord":          ("order_id",      0.88),
    "order":        ("order_id",      0.88),
    "inv":          ("invoice_id",    0.88),
    "invoice":      ("invoice_id",    0.88),
    "cus":          ("customer_id",   0.88),
    "cust":         ("customer_id",   0.88),
    "customer":     ("customer_id",   0.88),
    "usr":          ("user_id",       0.88),
    "user":         ("user_id",       0.88),
    "dept":         ("department_id", 0.85),
    "dep":          ("department_id", 0.85),
    "pos":          ("position_id",   0.60),
    "position":     ("position_id",   0.85),
    "badge":        ("badge_id",      0.88),
    "doc":          ("document_id",   0.88),
    "document":     ("document_id",   0.88),
    "job":          ("job_id",        0.85),
    "tok":          ("token",         0.85),
    "token":        ("token",         0.85),
    "notif":        ("notification_id", 0.82),
    "notification": ("notification_id", 0.82),
    "batch":        ("batch_id",      0.85),
    "prod":         ("product_id",    0.85),
    "product":      ("product_id",    0.85),
    "ticket":       ("ticket_id",     0.85),
    "tick":         ("ticket_id",     0.85),
}


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
    if PREFIXED_RESOURCE_ID_PATTERN.match(segment):
        return "prefixed_resource_id"

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
    # "_id" is produced when the JSON key is the bare word "id" — too generic
    # to override a resource-context name (employee_id, user_id, etc.)
    if payload_name and payload_name not in {"_id", "id"}:
        return payload_name, "payload", 0.95

    if detected_type in {"invoice_id", "payment_id", "employee_id", "order_id", "customer_id", "contract_id"}:
        return detected_type, "rules", 0.95

    if detected_type == "prefixed_resource_id":
        prefix = raw_value.split("_")[0].lower()
        if prefix in _PREFIX_TO_PARAM:
            param_name, confidence = _PREFIX_TO_PARAM[prefix]
            return param_name, "prefix_rules", confidence
        # Unknown prefix → low confidence so Groq is called
        return "resource_id", "prefix_rules_ambiguous", 0.45

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
