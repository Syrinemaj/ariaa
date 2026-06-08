"""
Upload routes.

/har            — parse + score only (sync, lightweight, no DB)
/har/normalized — parse + normalize (sync, no DB)
/har/analyze    — FULL pipeline: validate → save → enqueue Celery → return job_id

The full pipeline (/har/analyze) no longer blocks the HTTP handler.
Progress and result are polled via GET /jobs/{job_id}.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from pydantic import BaseModel

from app.auth.dependencies import require_admin_or_operator
from app.core.config import settings
from app.core.rate_limit import limiter
from app.db.redis_client import get_redis
from app.ingestion.service import process_har_file
from app.models.user import User
from app.normalization.service import normalize_entries
from app.security.upload_limits import save_har_file_with_limit

router = APIRouter(prefix="/upload", tags=["Upload"])

UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


class AnalyzeJobResponse(BaseModel):
    job_id: str
    status: str = "queued"
    file_name: str
    message: str


# ─── Lightweight sync endpoints ───────────────────────────────────────────────

@router.post("/har")
async def upload_har(
    file: UploadFile = File(...),
    current_user: User = Depends(require_admin_or_operator),
):
    file_id = str(uuid4())
    file_path = UPLOAD_DIR / f"{file_id}.har"
    await save_har_file_with_limit(upload_file=file, destination=file_path)

    entries = process_har_file(
        file_path=file_path,
        use_ai=True,
        only_candidates=True,
    )

    return {
        "file_id": file_id,
        "total_entries": len(entries),
        "entries": [entry.model_dump() for entry in entries],
    }


@router.post("/har/normalized")
async def upload_har_and_normalize(
    file: UploadFile = File(...),
    current_user: User = Depends(require_admin_or_operator),
):
    file_id = str(uuid4())
    file_path = UPLOAD_DIR / f"{file_id}.har"
    await save_har_file_with_limit(upload_file=file, destination=file_path)

    cleaned_entries = process_har_file(
        file_path=file_path,
        use_ai=True,
        only_candidates=True,
    )

    normalized_endpoints = normalize_entries(
        entries=cleaned_entries,
        use_ai=True,
        deduplicate=True,
    )

    return {
        "file_id": file_id,
        "cleaned_api_calls": len(cleaned_entries),
        "normalized_endpoints": len(normalized_endpoints),
        "endpoints": [endpoint.model_dump() for endpoint in normalized_endpoints],
    }


# ─── Async full pipeline ──────────────────────────────────────────────────────

@router.post("/har/analyze", response_model=AnalyzeJobResponse, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(settings.RATE_LIMIT_UPLOAD)
async def upload_har_and_analyze(
    request: Request,
    file: UploadFile = File(..., description="HAR file to analyse"),
    label: Optional[str] = Query(
        default=None,
        description="Human-readable name for this analysis run (e.g. 'Production API – June 2026'). Defaults to the uploaded file name.",
    ),
    current_user: User = Depends(require_admin_or_operator),
):
    """
    Accepts a HAR file, saves it, enqueues the full pipeline as a Celery task,
    and returns a job_id immediately (HTTP 202 Accepted).

    Poll GET /jobs/{job_id} for status and results.
    """
    file_id = str(uuid4())
    job_id = str(uuid4())
    file_path = UPLOAD_DIR / f"{file_id}.har"

    await save_har_file_with_limit(upload_file=file, destination=file_path)

    # Resolve the display name: label > original filename > generated id
    file_name = label.strip() if label and label.strip() else (file.filename or f"{file_id}.har")

    # Pre-create the job entry so /jobs/{job_id} works before the worker starts
    redis = get_redis()
    redis.setex(
        f"job:{job_id}",
        86_400,
        json.dumps({
            "job_id": job_id,
            "status": "queued",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }),
    )

    from app.workers.tasks.ingestion import process_har_pipeline
    process_har_pipeline.apply_async(
        kwargs={
            "job_id": job_id,
            "file_path": str(file_path),
            "file_name": file_name,
            "org_id": current_user.org_id,
            "user_id": current_user.id,
            "options": {
                "use_phase2_ai": True,
                "use_normalization_ai": True,
                "deduplicate": True,
            },
        },
        task_id=job_id,
    )

    return AnalyzeJobResponse(
        job_id=job_id,
        status="queued",
        file_name=file_name,
        message=f"Pipeline enqueued. Poll GET /jobs/{job_id} for status.",
    )
