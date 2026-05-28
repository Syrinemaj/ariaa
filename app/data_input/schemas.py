from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class UploadedDataFileResult(BaseModel):
    data_file_id: str
    file_name: str
    file_type: str
    rows_count: int
    columns: List[str]
    preview: List[Dict[str, Any]] = Field(default_factory=list)


class DataRowDTO(BaseModel):
    row_index: int
    raw_data: Dict[str, Any]
    normalized_data: Dict[str, Any] = Field(default_factory=dict)
    status: str = "pending"
    error_message: Optional[str] = None
