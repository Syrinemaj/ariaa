import re
from typing import Any, Dict, List

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_email(value: str) -> bool:
    return bool(EMAIL_PATTERN.match(value))


def validate_row_business_rules(row: Dict[str, Any], row_index: int) -> List[Dict[str, Any]]:
    errors = []
    email = row.get("email")

    if email and not validate_email(str(email)):
        errors.append({
            "row_index": row_index,
            "field_name": "email",
            "error_code": "INVALID_EMAIL",
            "message": "Invalid email format",
        })

    return errors
