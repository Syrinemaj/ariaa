import logging
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

logger = logging.getLogger(__name__)


def parse_excel_file(file_path: str | Path) -> List[Dict[str, Any]]:
    xl = pd.ExcelFile(file_path, engine="openpyxl")
    # BUG-015: silently ignoring extra sheets surprises users who put data on sheet 2
    if len(xl.sheet_names) > 1:
        logger.warning(
            "Excel file has %d sheets %s — only sheet '%s' will be processed; "
            "data on other sheets is ignored.",
            len(xl.sheet_names),
            xl.sheet_names,
            xl.sheet_names[0],
        )
    df = xl.parse(xl.sheet_names[0])
    df = df.fillna("")
    return df.to_dict(orient="records")
