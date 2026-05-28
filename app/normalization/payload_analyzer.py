from typing import Any, Optional


def _flatten_dict(data: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}

    def walk(value: Any, prefix: str = "") -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                full_key = f"{prefix}.{key}" if prefix else key
                result[full_key] = child
                walk(child, full_key)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{prefix}[{index}]")

    walk(data)
    return result


def _normalize_key_to_parameter_name(key: str) -> str:
    key = key.split(".")[-1]
    key = key.replace("-", "_")

    result = ""
    for index, char in enumerate(key):
        if char.isupper() and index > 0:
            result += "_"
        result += char.lower()

    if result.endswith("_id"):
        return result

    if result.endswith("id"):
        return result[:-2] + "_id"

    return result


def find_parameter_name_from_payload(
    raw_value: str,
    request_body: Any = None,
    response_body: Any = None,
) -> Optional[str]:
    for payload in [request_body, response_body]:
        if payload is None:
            continue

        flattened = _flatten_dict(payload)

        for key, value in flattened.items():
            if str(value) == str(raw_value):
                return _normalize_key_to_parameter_name(key)

    return None
