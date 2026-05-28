from typing import Any, Dict


def build_static_lookup() -> Dict[str, Dict[str, Any]]:
    return {
        "departmentId": {
            "IT": 1,
            "Finance": 2,
            "HR": 3,
            "Sales": 4,
        },
        "managerId": {
            "Ahmed": 10,
            "Karim": 11,
            "Sarra": 12,
        },
    }
