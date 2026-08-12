from typing import Any, Dict, Optional, Tuple

from app.planner.models import PlanStep


def _to_snake_case(value: str) -> str:
    result = ""
    for index, char in enumerate(value):
        if char.isupper() and index > 0:
            result += "_"
        result += char.lower()
    return result.replace("-", "_")


def _candidate_keys(schema_field: str) -> list[str]:
    snake = _to_snake_case(schema_field)
    return list({schema_field, snake, schema_field.lower(), snake.replace("_", "")})


def _coerce_value(value: Any, field_schema: Dict[str, Any]) -> Any:
    """Coerce value to match the JSON Schema type declared for the field.

    CSV rows and API responses often carry integers where the schema says
    "string" (e.g. departmentId: 10 vs type: "string").  Silently convert
    rather than failing with a jsonschema type error at execution time.
    """
    expected = field_schema.get("type")
    if expected == "string" and not isinstance(value, str):
        return str(value)
    if expected == "integer" and isinstance(value, str):
        try:
            return int(value)
        except (ValueError, TypeError):
            return value
    if expected == "number" and isinstance(value, str):
        try:
            return float(value)
        except (ValueError, TypeError):
            return value
    if expected == "boolean" and isinstance(value, str):
        return value.lower() in ("true", "1", "yes")
    return value


def _invert_field_mapping(field_mapping: Dict[str, Any]) -> Dict[str, Tuple[str, Optional[dict]]]:
    """
    step.field_mapping is keyed by SOURCE column (row field / CSV column),
    e.g. {"prénom": "first_name", "type_contrat": null} — see
    plan_generator.py's few-shot examples. map_payload_for_step needs the
    reverse direction (target API param -> source), so build that once per
    call rather than re-deriving it inline for every schema property.

    Two source-column value shapes are supported:
    - a plain string: direct rename, target value = input_row[source_column]
    - a dict {"maps_to", "when_equals", "then", "else"}: conditional value,
      derived from source_column's value rather than copied — e.g. a business
      rule like "approve automatically the ones of type congé" from a
      free-text instruction (see plan_generator.py's EXEMPLE 4). Not a
      general expression language on purpose — no eval(), just one equality
      check — this is the minimal shape that covers a same-row conditional
      without opening up arbitrary code execution from LLM output.
    None values (source column not used by this step) are skipped.
    """
    inverted: Dict[str, Tuple[str, Optional[dict]]] = {}
    for source_column, rule in (field_mapping or {}).items():
        if rule is None:
            continue
        if isinstance(rule, str):
            inverted[rule] = (source_column, None)
        elif isinstance(rule, dict) and rule.get("maps_to"):
            inverted[rule["maps_to"]] = (source_column, rule)
    return inverted


def _resolve_conditional(rule: dict, source_column: str, input_row: Dict[str, Any]) -> Optional[Any]:
    actual = input_row.get(source_column)
    expected = rule.get("when_equals")
    matches = (
        actual is not None
        and expected is not None
        and str(actual).strip().lower() == str(expected).strip().lower()
    )
    return rule.get("then") if matches else rule.get("else")


def map_payload_for_step(
    step: PlanStep,
    input_row: Dict[str, Any],
    state: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, str]]:
    """
    Returns (payload, field_sources) — field_sources[field_name] is one of
    "field_mapping" (explicit rename/conditional from the plan), "input_row"
    (matched by name against the row data), or "state" (matched by name
    against a prior step's response in this row). Callers use field_sources
    to flag a specific failure mode: an update step (PATCH/PUT) whose value
    was never actually provided by the row or the plan, only echoed back
    from what a previous step already returned — see
    batch_processor.py::_check_stale_update_fields.
    """
    if not step.request_schema:
        return {}, {}

    properties = step.request_schema.get("properties", {})
    payload: Dict[str, Any] = {}
    field_sources: Dict[str, str] = {}
    mapping_by_target = _invert_field_mapping(step.field_mapping)

    for field_name, field_schema in properties.items():
        if field_name in mapping_by_target:
            source_column, rule = mapping_by_target[field_name]
            if rule is not None:
                value = _resolve_conditional(rule, source_column, input_row)
                if value is not None:
                    payload[field_name] = _coerce_value(value, field_schema)
                    field_sources[field_name] = "field_mapping"
                continue
            if source_column in input_row:
                payload[field_name] = _coerce_value(input_row[source_column], field_schema)
                field_sources[field_name] = "field_mapping"
                continue
            # Rename target named but source column absent from this row —
            # fall through to the generic name-matching below.

        candidates = _candidate_keys(field_name)
        for candidate in candidates:
            if candidate in input_row:
                payload[field_name] = _coerce_value(input_row[candidate], field_schema)
                field_sources[field_name] = "input_row"
                break
            if candidate in state:
                payload[field_name] = _coerce_value(state[candidate], field_schema)
                field_sources[field_name] = "state"
                break

    return payload, field_sources
