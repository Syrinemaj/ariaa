from typing import Any, Dict, List

VALID_CONTRACT_TYPES = {"CDI", "CDD", "STAGE", "FREELANCE"}


def validate_contract_type(row: Dict[str, Any], row_index: int) -> List[Dict[str, Any]]:
    errors = []
    value = row.get("contractType")

    if value and str(value).upper() not in VALID_CONTRACT_TYPES:
        errors.append({
            "row_index": row_index,
            "field_name": "contractType",
            "error_code": "INVALID_CONTRACT_TYPE",
            "message": f"Invalid contract type: {value}",
        })

    return errors
