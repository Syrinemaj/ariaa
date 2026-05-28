from pathlib import Path
from typing import Any, Dict, List

import pandas as pd


def parse_excel_file(file_path: str | Path) -> List[Dict[str, Any]]:
    df = pd.read_excel(file_path, engine="openpyxl")
    df = df.fillna("")
    return df.to_dict(orient="records")
