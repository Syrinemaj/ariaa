from typing import Any, Dict

# BUG-014: these keys control execution routing — a malicious API response
# must not be allowed to overwrite them and redirect subsequent calls.
_FORBIDDEN_STATE_KEYS = frozenset({
    "base_url", "auth_headers", "connection_id", "job_id", "automation_run_id",
    "data_file_id", "org_id", "batch_size", "batch_number",
})

# A "Create <Entity>" step's response id becomes <entity>Id / <entity>_id in
# state, so a later step's foreign-key field (employee_id, contract_id, ...)
# can be found by map_payload_for_step's name-matching even though the
# response itself only ever calls it "id". Single source of truth for this
# heuristic — also used by app/automation/payload_mapper.py::
# required_input_fields() to statically predict which fields a later step
# will get for free versus which the caller must actually supply, without
# running anything.
ENTITY_ID_ALIASES: Dict[str, tuple[str, ...]] = {
    "create_employee": ("employeeId", "employee_id"),
    "employee_create": ("employeeId", "employee_id"),
    "add_employee": ("employeeId", "employee_id"),
    "create_contract": ("contractId", "contract_id"),
    "contract_create": ("contractId", "contract_id"),
    "add_contract": ("contractId", "contract_id"),
}


def normalize_action(action: str | None) -> str:
    """'Create Employee' -> 'create_employee'."""
    return (action or "").lower().replace(" ", "_").replace("-", "_")


def update_state_from_response(
    state: Dict[str, Any],
    response_payload: Any,
    action: str | None = None,
) -> Dict[str, Any]:
    if not isinstance(response_payload, dict):
        return state

    for key, value in response_payload.items():
        if key not in _FORBIDDEN_STATE_KEYS:
            state[key] = value

    if "id" in response_payload:
        state["last_id"] = response_payload["id"]

    for alias in ENTITY_ID_ALIASES.get(normalize_action(action), ()):
        state[alias] = response_payload.get("id")

    return state
