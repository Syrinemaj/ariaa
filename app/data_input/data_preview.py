from typing import Any, Dict, List


def build_preview(rows: List[Dict[str, Any]], limit: int = 5) -> List[Dict[str, Any]]:
    return rows[:limit]
