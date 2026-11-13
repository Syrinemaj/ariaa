from pathlib import Path
from typing import Any, Dict, List

import pandas as pd


def _repair_mojibake(value: Any) -> Any:
    """Undo "UTF-8 bytes read as Latin-1" corruption (e.g. "employÃ©" -> "employé").
    This is common when a CSV is round-tripped through Excel/another tool on a
    Windows locale before upload. The round-trip only succeeds for genuinely
    corrupted text — correctly-encoded UTF-8 accented text raises
    UnicodeDecodeError on this specific re-encode and is left untouched, so
    this can't silently corrupt already-valid text.
    """
    if not isinstance(value, str):
        return value
    try:
        return value.encode("latin-1").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return value


def parse_csv_file(file_path: str | Path) -> List[Dict[str, Any]]:
    df = pd.read_csv(file_path)
    df = df.fillna("")
    df.columns = [_repair_mojibake(c) for c in df.columns]
    df = df.map(_repair_mojibake)
    return df.to_dict(orient="records")
