import json
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("aria")
logger.setLevel(logging.INFO)

if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(handler)


def log_event(event_name: str, payload: Optional[Dict[str, Any]] = None) -> None:
    logger.info(json.dumps({"event": event_name, "payload": payload or {}}, ensure_ascii=False))


def log_error(event_name: str, error: Exception, payload: Optional[Dict[str, Any]] = None) -> None:
    logger.error(json.dumps({"event": event_name, "error": str(error), "payload": payload or {}}, ensure_ascii=False))
