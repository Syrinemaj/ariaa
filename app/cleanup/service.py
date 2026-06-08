"""
Upload cleanup service — removes expired uploaded files (Fix 14.3).

Replaces print() with structlog so cleanup runs are captured in the same
JSON log stream as everything else.
"""
from __future__ import annotations

from app.cleanup.uploaded_files_cleanup import cleanup_upload_directory
from app.core.logging import get_logger

logger = get_logger(__name__)


def run_upload_cleanup(dry_run: bool = False) -> dict:
    """Run the upload directory cleanup and log the result."""
    result = cleanup_upload_directory(dry_run=dry_run)

    logger.info(
        "upload_cleanup.complete",
        directory=result.get("directory"),
        deleted_count=result.get("deleted_count", 0),
        skipped_count=result.get("skipped_count", 0),
        dry_run=result.get("dry_run"),
    )

    return result
