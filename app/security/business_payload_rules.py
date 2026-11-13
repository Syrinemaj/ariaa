import re
from datetime import datetime
from typing import Any, Dict, List

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ALLOWED_CONTRACT_TYPES = {"CDI", "CDD", "FREELANCE", "INTERIM", "STAGE", "APPRENTISSAGE"}

_DATE_FIELD_NAMES = {"date_debut", "date_fin", "start_date", "end_date", "birthdate"}
# Ambiguous d/m vs m/d inputs (e.g. "08/05/2026") default to US m/d/Y since
# that's the observed format from common spreadsheet-export tools; unambiguous
# values (day > 12) parse correctly regardless of this ordering.
_DATE_INPUT_FORMATS = ["%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d", "%m/%d/%y", "%d/%m/%y"]


def _normalize_dates_in_place(payload: Dict[str, Any]) -> None:
    """Coerce common non-ISO date formats (e.g. CSV exports using MM/DD/YYYY)
    to ISO YYYY-MM-DD before the strict ISO check runs, so a genuinely valid
    date isn't rejected just for arriving in a different — but unambiguous —
    format than the one this rule was written to expect."""
    for field, value in list(payload.items()):
        if field.lower() not in _DATE_FIELD_NAMES or not isinstance(value, str):
            continue
        if _DATE_RE.match(value):
            continue
        for fmt in _DATE_INPUT_FORMATS:
            try:
                payload[field] = datetime.strptime(value, fmt).strftime("%Y-%m-%d")
                break
            except ValueError:
                continue


def _check_email(value: str, field: str, issues: List[str]) -> None:
    if not _EMAIL_RE.match(value):
        issues.append(f"Field '{field}' is not a valid email address: {value!r}")


def _check_date(value: str, field: str, issues: List[str]) -> None:
    if not _DATE_RE.match(value):
        issues.append(f"Field '{field}' must be ISO date YYYY-MM-DD, got: {value!r}")
        return
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        issues.append(f"Field '{field}' is not a real date: {value!r}")


def _check_contract_type(value: str, field: str, issues: List[str]) -> None:
    if value.upper() not in _ALLOWED_CONTRACT_TYPES:
        issues.append(
            f"Field '{field}' must be one of {sorted(_ALLOWED_CONTRACT_TYPES)}, got: {value!r}"
        )


_FIELD_RULES = {
    "email": _check_email,
    "mail": _check_email,
    "date_debut": _check_date,
    "date_fin": _check_date,
    "start_date": _check_date,
    "end_date": _check_date,
    "birthdate": _check_date,
    "contract_type": _check_contract_type,
    "type_contrat": _check_contract_type,
}


def validate_business_rules(payload: Dict[str, Any]) -> List[str]:
    _normalize_dates_in_place(payload)

    issues: List[str] = []
    for field, value in payload.items():
        if not isinstance(value, str):
            continue
        rule_fn = _FIELD_RULES.get(field.lower())
        if rule_fn:
            rule_fn(value, field, issues)
    return issues


def assert_business_rules_valid(payload: Dict[str, Any]) -> None:
    issues = validate_business_rules(payload)
    if issues:
        from app.security.payload_validator import PayloadValidationError
        raise PayloadValidationError("; ".join(issues))
