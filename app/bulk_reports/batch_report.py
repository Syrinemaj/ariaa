from sqlalchemy.orm import Session

from app.models.bulk_batch import BulkBatch


def get_batch_summary(db: Session, automation_run_id: str) -> list[dict]:
    batches = (
        db.query(BulkBatch)
        .filter(BulkBatch.automation_run_id == automation_run_id)
        .order_by(BulkBatch.batch_number.asc())
        .all()
    )

    return [
        {
            "batch_number": batch.batch_number,
            "start_row": batch.start_row,
            "end_row": batch.end_row,
            "status": batch.status,
            "success_count": batch.success_count,
            "failed_count": batch.failed_count,
        }
        for batch in batches
    ]
