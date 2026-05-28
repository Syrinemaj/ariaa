from sqlalchemy.orm import Session

from app.models.bulk_batch import BulkBatch, BulkBatchRow


def get_failed_rows(db: Session, automation_run_id: str) -> list[dict]:
    rows = (
        db.query(BulkBatchRow, BulkBatch)
        .join(BulkBatch, BulkBatch.id == BulkBatchRow.batch_id)
        .filter(
            BulkBatch.automation_run_id == automation_run_id,
            BulkBatchRow.status == "failed",
        )
        .all()
    )

    return [
        {
            "batch_number": batch.batch_number,
            "row_index": row.row_index,
            "status": row.status,
            "error_message": row.error_message,
            "result": row.result_json,
        }
        for row, batch in rows
    ]
