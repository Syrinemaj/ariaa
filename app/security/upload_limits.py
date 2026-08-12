from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings


HAR_ALLOWED_SUFFIXES = {".har"}
BULK_ALLOWED_SUFFIXES = {".csv", ".xlsx", ".xls"}


def mb_to_bytes(value: int) -> int:
    return value * 1024 * 1024


def validate_file_extension(filename: str, allowed_suffixes: set[str]) -> None:
    suffix = Path(filename).suffix.lower()

    if suffix not in allowed_suffixes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type. Allowed: {', '.join(sorted(allowed_suffixes))}",
        )


async def save_upload_file_with_limit(
    upload_file: UploadFile,
    destination: Path,
    allowed_suffixes: set[str],
    max_size_mb: int | None = None,
) -> int:
    if not upload_file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing filename",
        )

    validate_file_extension(upload_file.filename, allowed_suffixes)

    max_size_bytes = mb_to_bytes(max_size_mb) if max_size_mb is not None else None
    total_size = 0

    destination.parent.mkdir(parents=True, exist_ok=True)

    with destination.open("wb") as buffer:
        while True:
            chunk = await upload_file.read(1024 * 1024)

            if not chunk:
                break

            total_size += len(chunk)

            if max_size_bytes is not None and total_size > max_size_bytes:
                destination.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File too large. Max size is {max_size_mb} MB",
                )

            buffer.write(chunk)

    return total_size


async def save_har_file_with_limit(upload_file: UploadFile, destination: Path) -> int:
    # No size cap on HAR ingestion — files can be arbitrarily large.
    return await save_upload_file_with_limit(
        upload_file=upload_file,
        destination=destination,
        allowed_suffixes=HAR_ALLOWED_SUFFIXES,
    )


async def save_bulk_file_with_limit(upload_file: UploadFile, destination: Path) -> int:
    return await save_upload_file_with_limit(
        upload_file=upload_file,
        destination=destination,
        max_size_mb=settings.BULK_FILE_MAX_SIZE_MB,
        allowed_suffixes=BULK_ALLOWED_SUFFIXES,
    )
