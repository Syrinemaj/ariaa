from sqlalchemy.orm import Session

from app.models.idempotency import IdempotencyRecord


def get_idempotency_record(
    db: Session,
    idempotency_key: str,
    endpoint_key: str,
) -> IdempotencyRecord | None:
    return (
        db.query(IdempotencyRecord)
        .filter(
            IdempotencyRecord.idempotency_key == idempotency_key,
            IdempotencyRecord.endpoint_key == endpoint_key,
        )
        .first()
    )


def save_idempotency_record(
    db: Session,
    automation_run_id: str,
    data_row_id: str | None,
    row_index: int,
    endpoint_key: str,
    idempotency_key: str,
    status: str,
    response_reference: dict,
) -> IdempotencyRecord:
    record = IdempotencyRecord(
        automation_run_id=automation_run_id,
        data_row_id=data_row_id,
        row_index=row_index,
        endpoint_key=endpoint_key,
        idempotency_key=idempotency_key,
        status=status,
        response_reference=response_reference,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record
