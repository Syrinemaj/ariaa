from datetime import datetime, timedelta
from pathlib import Path

from app.core.config import settings


def should_delete_file(file_path: Path, ttl: timedelta) -> bool:
    if not file_path.exists():
        return False
    modified_at = datetime.utcfromtimestamp(file_path.stat().st_mtime)
    return modified_at < datetime.utcnow() - ttl


def cleanup_upload_directory(
    upload_dir: str | None = None,
    dry_run: bool | None = None,
) -> dict:
    directory = Path(upload_dir or settings.UPLOAD_DIR)
    is_dry_run = settings.CLEANUP_DRY_RUN if dry_run is None else dry_run

    if not directory.exists():
        return {
            "directory": str(directory),
            "deleted_files": [],
            "skipped_files": [],
            "deleted_count": 0,
            "skipped_count": 0,
            "dry_run": is_dry_run,
            "message": "Upload directory does not exist.",
        }

    ttl = timedelta(days=settings.UPLOAD_FILE_TTL_DAYS)
    deleted_files: list[str] = []
    skipped_files: list[str] = []

    for file_path in directory.rglob("*"):
        if not file_path.is_file():
            continue

        if should_delete_file(file_path, ttl):
            deleted_files.append(str(file_path))
            if not is_dry_run:
                file_path.unlink(missing_ok=True)
        else:
            skipped_files.append(str(file_path))

    return {
        "directory": str(directory),
        "deleted_files": deleted_files,
        "skipped_files": skipped_files,
        "deleted_count": len(deleted_files),
        "skipped_count": len(skipped_files),
        "dry_run": is_dry_run,
    }
