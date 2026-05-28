from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.data_input.csv_parser import parse_csv_file
from app.data_input.data_preview import build_preview
from app.data_input.excel_parser import parse_excel_file
from app.data_input.schemas import UploadedDataFileResult
from app.models.data_file import DataFile, DataRow


def parse_data_file(file_path: str | Path) -> List[Dict[str, Any]]:
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix == ".csv":
        return parse_csv_file(path)

    if suffix in {".xlsx", ".xls"}:
        return parse_excel_file(path)

    raise ValueError("Unsupported file type. Only CSV and Excel are allowed.")


def save_uploaded_data_file(
    db: Session,
    analysis_run_id: str,
    file_name: str,
    file_path: str | Path,
    org_id: str = "",
    created_by_user_id: Optional[str] = None,
) -> UploadedDataFileResult:
    rows = parse_data_file(file_path)

    columns = list(rows[0].keys()) if rows else []
    file_type = Path(file_name).suffix.lower().replace(".", "")

    data_file = DataFile(
        analysis_run_id=analysis_run_id,
        file_name=file_name,
        file_type=file_type,
        rows_count=len(rows),
        columns=columns,
        status="parsed",
        org_id=org_id,
        created_by_user_id=created_by_user_id,
    )

    db.add(data_file)
    db.flush()

    for index, row in enumerate(rows, start=1):
        db.add(DataRow(
            data_file_id=data_file.id,
            row_index=index,
            raw_data=row,
            normalized_data={},
            status="pending",
        ))

    db.commit()
    db.refresh(data_file)

    return UploadedDataFileResult(
        data_file_id=data_file.id,
        file_name=file_name,
        file_type=file_type,
        rows_count=len(rows),
        columns=columns,
        preview=build_preview(rows),
    )


def get_data_rows(
    db: Session,
    data_file_id: str,
    only_valid: bool = False,
) -> list[DataRow]:
    query = db.query(DataRow).filter(DataRow.data_file_id == data_file_id)

    if only_valid:
        query = query.filter(DataRow.status == "valid")

    return query.order_by(DataRow.row_index.asc()).all()
