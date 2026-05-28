from typing import Any, Dict


def update_state_from_response(
    state: Dict[str, Any],
    response_payload: Any,
    action: str | None = None,
) -> Dict[str, Any]:
    if not isinstance(response_payload, dict):
        return state

    for key, value in response_payload.items():
        state[key] = value

    if "id" in response_payload:
        state["last_id"] = response_payload["id"]

    if action == "create_employee":
        state["employeeId"] = response_payload.get("id")
        state["employee_id"] = response_payload.get("id")

    if action == "create_contract":
        state["contractId"] = response_payload.get("id")
        state["contract_id"] = response_payload.get("id")

    return state
