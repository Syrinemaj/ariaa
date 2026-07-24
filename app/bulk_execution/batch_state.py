from typing import Any, Dict

# BUG-014: these keys control execution routing — a malicious API response
# must not be allowed to overwrite them and redirect subsequent calls.
_FORBIDDEN_STATE_KEYS = frozenset({
    "base_url", "auth_headers", "job_id", "automation_run_id",
    "data_file_id", "org_id", "batch_size", "batch_number",
})


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

    # Normalize action: "Create Employee" → "create_employee"
    action_norm = (action or "").lower().replace(" ", "_").replace("-", "_")

    if action_norm in ("create_employee", "employee_create", "add_employee"):
        state["employeeId"] = response_payload.get("id")
        state["employee_id"] = response_payload.get("id")

    if action_norm in ("create_contract", "contract_create", "add_contract"):
        state["contractId"] = response_payload.get("id")
        state["contract_id"] = response_payload.get("id")

    return state
