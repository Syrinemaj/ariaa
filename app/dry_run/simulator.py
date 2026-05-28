from sqlalchemy.orm import Session

from app.dry_run.estimation import estimate_api_calls, estimate_duration_seconds
from app.models.data_file import DataRow


def simulate_bulk_execution(
    db: Session,
    data_file_id: str,
    plan: dict,
    allow_partial_execution: bool = False,
) -> dict:
    total_rows = db.query(DataRow).filter(DataRow.data_file_id == data_file_id).count()
    valid_rows = (
        db.query(DataRow)
        .filter(DataRow.data_file_id == data_file_id, DataRow.status == "valid")
        .count()
    )

    invalid_rows = total_rows - valid_rows
    steps_count = len(plan.get("steps", []))
    estimated_calls = estimate_api_calls(valid_rows, steps_count)
    estimated_duration = estimate_duration_seconds(estimated_calls)
    ready = invalid_rows == 0 or allow_partial_execution

    return {
        "mode": "dry_run",
        "total_rows": total_rows,
        "valid_rows": valid_rows,
        "invalid_rows": invalid_rows,
        "steps_count": steps_count,
        "estimated_api_calls": estimated_calls,
        "estimated_duration_seconds": estimated_duration,
        "ready_for_execution": ready,
        "allow_partial_execution": allow_partial_execution,
        "recommendation": (
            "Correct invalid rows before execution."
            if invalid_rows > 0 and not allow_partial_execution
            else "Execution can proceed."
        ),
    }
