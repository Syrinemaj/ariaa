from sqlalchemy.orm import Session

from app.dry_run.simulator import simulate_bulk_execution


def run_bulk_dry_run(
    db: Session,
    data_file_id: str,
    plan: dict,
    allow_partial_execution: bool = False,
) -> dict:
    return simulate_bulk_execution(
        db=db,
        data_file_id=data_file_id,
        plan=plan,
        allow_partial_execution=allow_partial_execution,
    )
