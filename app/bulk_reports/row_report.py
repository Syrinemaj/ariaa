from sqlalchemy.orm import Session

from app.models.bulk_batch import BulkBatch, BulkBatchRow


def _error_code_and_message(row: BulkBatchRow) -> tuple[str, str]:
    """error_code/message as the frontend (BulkPage.tsx, ReportsPage.tsx) and
    the errors.csv download (app/api/bulk.py) actually read — previously this
    returned error_message/result/status instead, so both call sites read
    undefined keys: the CSV endpoint raised a KeyError (never reachable
    before this fix) and the report table silently rendered blank cells.

    result_json["_row_error"] (set in batch_executor.py) carries the precise
    {error_code, message} for rows that failed after this fix shipped;
    row.error_message is the fallback for anything written before that.
    """
    detail = (row.result_json or {}).get("_row_error")
    if isinstance(detail, dict) and detail.get("message"):
        return str(detail.get("error_code") or "ERROR"), str(detail["message"])
    return "ERROR", row.error_message or "Execution failed"


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

    result = []
    for row, batch in rows:
        error_code, message = _error_code_and_message(row)
        result.append({
            "batch_number": batch.batch_number,
            "row_index": row.row_index,
            "error_code": error_code,
            "message": message,
        })
    return result


def get_duplicate_rows(db: Session, automation_run_id: str) -> list[dict]:
    """Rows whose create 409'd as 'already exists' but were auto-resolved to
    the existing record (status='success_duplicate', see batch_executor.py)
    — these are NOT failures (the row completed, downstream steps ran), but
    are worth surfacing distinctly so an operator can tell "we reused an
    existing record" apart from "we created a brand new one"."""
    rows = (
        db.query(BulkBatchRow, BulkBatch)
        .join(BulkBatch, BulkBatch.id == BulkBatchRow.batch_id)
        .filter(
            BulkBatch.automation_run_id == automation_run_id,
            BulkBatchRow.status == "success_duplicate",
        )
        .all()
    )

    return [
        {
            "batch_number": batch.batch_number,
            "row_index": row.row_index,
            "error_code": "DUPLICATE_RESOLVED",
            "message": "Resolved to an existing record instead of creating a new one.",
        }
        for row, batch in rows
    ]
