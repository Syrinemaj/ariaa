"""
Re-exports app.bulk_execution.batch_state.update_state_from_response — Simple
Automation and Bulk Automation used to carry two separate implementations of
this function, and they'd quietly diverged: the bulk version renames a
"Create Employee" step's response id to state["employee_id"] (and similarly
for "Create Contract" → state["contract_id"]) so a later step's
employee_id/contract_id field can be found by map_payload_for_step's
name-matching; the Simple Automation copy here only ever did a literal
field-by-field copy (state["id"], state["last_id"]) with no such renaming —
so a plan like "create an employee, then submit a leave request for them"
always failed step 2 with "employee_id is a required property", even though
the identical two-step bulk plan worked. One function, one behavior, now.
"""
from app.bulk_execution.batch_state import update_state_from_response

__all__ = ["update_state_from_response"]
