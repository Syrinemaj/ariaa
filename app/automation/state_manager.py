from typing import Any, Dict


def update_state_from_response(
    state: Dict[str, Any],
    response_payload: Any,
) -> Dict[str, Any]:
    if not isinstance(response_payload, dict):
        return state

    for key, value in response_payload.items():
        state[key] = value
        if key == "id":
            state["last_id"] = value

    return state
