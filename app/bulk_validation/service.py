from sqlalchemy.orm import Session

from app.bulk_validation.business_rules import validate_contract_type
from app.bulk_validation.row_validator import validate_row_business_rules
from app.bulk_validation.schema_validator import validate_row_against_plan
from app.mapping.field_mapper import apply_mapping_to_row
from app.mapping.service import get_approved_mappings
from app.models.bulk_validation import BulkValidationError, BulkValidationRun
from app.models.data_file import DataRow
from app.reference_resolution.service import resolve_row_references


def validate_bulk_data(
    db: Session,
    analysis_run_id: str,
    data_file_id: str,
    plan: dict,
) -> dict:
    rows = (
        db.query(DataRow)
        .filter(DataRow.data_file_id == data_file_id)
        .order_by(DataRow.row_index.asc())
        .all()
    )

    mappings = get_approved_mappings(db=db, analysis_run_id=analysis_run_id)

    validation_run = BulkValidationRun(
        data_file_id=data_file_id,
        total_rows=len(rows),
        valid_rows=0,
        invalid_rows=0,
        status="running",
    )
    db.add(validation_run)
    db.flush()

    valid_count = 0
    invalid_count = 0
    all_errors = []

    for row in rows:
        mapped = apply_mapping_to_row(row=row.raw_data, mappings=mappings)
        resolved = resolve_row_references(mapped)

        errors = []
        errors.extend(validate_row_against_plan(resolved, plan, row.row_index))
        errors.extend(validate_row_business_rules(resolved, row.row_index))
        errors.extend(validate_contract_type(resolved, row.row_index))

        row.normalized_data = resolved

        if errors:
            row.status = "invalid"
            row.error_message = "; ".join(e["message"] for e in errors)
            invalid_count += 1

            for error in errors:
                db.add(BulkValidationError(
                    validation_run_id=validation_run.id,
                    row_index=error["row_index"],
                    field_name=error.get("field_name"),
                    error_code=error["error_code"],
                    message=error["message"],
                ))
            all_errors.extend(errors)
        else:
            row.status = "valid"
            row.error_message = None
            valid_count += 1

    validation_run.valid_rows = valid_count
    validation_run.invalid_rows = invalid_count
    validation_run.status = "completed" if invalid_count == 0 else "failed"

    db.commit()
    db.refresh(validation_run)

    return {
        "validation_run_id": validation_run.id,
        "data_file_id": data_file_id,
        "total_rows": len(rows),
        "valid_rows": valid_count,
        "invalid_rows": invalid_count,
        "ready_for_execution": invalid_count == 0,
        "can_execute_partial": valid_count > 0,
        "errors": all_errors,
    }
