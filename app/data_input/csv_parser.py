from pathlib import Path
from typing import Any, Dict, List

import pandas as pd


def parse_csv_file(file_path: str | Path) -> List[Dict[str, Any]]:
    df = pd.read_csv(file_path)
    df = df.fillna("")
    return df.to_dict(orient="records")
