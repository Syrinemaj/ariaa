from typing import Any, List

from app.planner.models import PlanStep


class PayloadValidationError(Exception):
    pass


def validate_payload_against_schema(
    step: PlanStep,
    payload: dict[str, Any],
) -> List[str]:
    if not step.request_schema:
        return []

    try:
        from jsonschema import Draft202012Validator
        validator = Draft202012Validator(step.request_schema)
        return [
            f"{'.'.join(str(p) for p in error.absolute_path) or error.validator}: {error.message}"
            for error in validator.iter_errors(payload)
        ]
    except ImportError:
        # Fallback: basic required-field check if jsonschema not installed
        issues: List[str] = []
        required_fields = step.request_schema.get("required", [])
        for field in required_fields:
            if field not in payload:
                issues.append(f"Missing required field '{field}' for {step.canonical_key}")
        return issues


def assert_payload_valid(step: PlanStep, payload: dict[str, Any]) -> None:
    issues = validate_payload_against_schema(step=step, payload=payload)
    if issues:
        raise PayloadValidationError("; ".join(issues))
