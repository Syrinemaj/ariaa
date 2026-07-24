import csv
import io
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.approval.approval_guard import ApprovalRequiredError
from app.audit.events import AuditEvent
from app.audit.service import log_audit_event
from app.auth.dependencies import require_admin_or_operator
from app.bulk_execution.resume import resume_job
from app.bulk_execution.service import execute_valid_rows_in_batches
from app.bulk_reports.service import build_bulk_report
from app.bulk_validation.service import validate_bulk_data
from app.core.config import settings
from app.core.rate_limit import limiter
from app.data_input.service import save_uploaded_data_file
from app.db.redis_client import get_redis
from app.db.session import get_sync_db
from app.dry_run.service import run_bulk_dry_run
from app.mapping.service import suggest_and_save_mappings
from app.models.analysis_run import AnalysisRun
from app.models.approval import AutomationApproval
from app.models.automation import AutomationRun
from app.models.bulk_validation import BulkValidationRun
from app.models.data_file import DataFile
from app.models.user import User, UserRole
from app.planner.models import AutomationPlan
from app.security.ssrf_guard import validate_target_url
from app.security.upload_limits import save_bulk_file_with_limit

router = APIRouter(prefix="/bulk", tags=["Bulk Automation"])

UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Redis lock TTL for idempotency guard (seconds)
_EXEC_LOCK_TTL = 30


# ── Ownership helpers ─────────────────────────────────────────────────────────

def _assert_analysis_run_org(db: Session, analysis_run_id: str, org_id: str) -> AnalysisRun:
    """Raise 404 if the AnalysisRun doesn't exist or belongs to a different org."""
    run = db.query(AnalysisRun).filter(
        AnalysisRun.id == analysis_run_id,
        AnalysisRun.org_id == org_id,
    ).first()
    if not run:
        raise HTTPException(status_code=404, detail="Analysis run not found")
    return run


def _assert_data_file_org(db: Session, data_file_id: str, org_id: str) -> DataFile:
    """Raise 404 if the DataFile doesn't exist or belongs to a different org."""
    df = db.query(DataFile).filter(
        DataFile.id == data_file_id,
        DataFile.org_id == org_id,
    ).first()
    if not df:
        raise HTTPException(status_code=404, detail="Data file not found")
    return df


def _assert_automation_run_org(db: Session, automation_run_id: str, org_id: str) -> AutomationRun:
    """Raise 404 if the AutomationRun doesn't exist or belongs to a different org."""
    run = db.query(AutomationRun).filter(
        AutomationRun.id == automation_run_id,
        AutomationRun.org_id == org_id,
    ).first()
    if not run:
        raise HTTPException(status_code=404, detail="Automation run not found")
    return run


def _sanitize_csv_cell(value: str) -> str:
    """Neutralise spreadsheet formula injection (=, +, -, @, tab, CR at start)."""
    if value and value[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


# ── Request / Response models ─────────────────────────────────────────────────

class MappingSuggestRequest(BaseModel):
    analysis_run_id: str
    data_file_id: str
    plan: Dict[str, Any]


class BulkValidationRequest(BaseModel):
    analysis_run_id: str
    data_file_id: str
    plan: Dict[str, Any]


class BulkDryRunRequest(BaseModel):
    data_file_id: str
    plan: Dict[str, Any]
    allow_partial_execution: bool = False


class BulkExecuteRequest(BaseModel):
    plan: AutomationPlan
    data_file_id: str
    base_url: str
    auth_headers: Dict[str, str]
    dry_run: bool = True
    # BUG-013: constrain batch_size to avoid divide-by-zero and runaway jobs
    batch_size: int = Field(default=settings.BULK_BATCH_SIZE, ge=1, le=500)
    allow_partial_execution: bool = True
    approval_granted: bool = False
    resume: bool = False
    existing_automation_run_id: Optional[str] = None


class BulkResumeRequest(BaseModel):
    job_id: str
    automation_run_id: str
    data_file_id: str
    plan: AutomationPlan
    base_url: str
    auth_headers: Dict[str, str]
    dry_run: bool = True
    # BUG-013: same constraint
    batch_size: int = Field(default=settings.BULK_BATCH_SIZE, ge=1, le=500)


class BulkExecuteResponse(BaseModel):
    job_id: str
    automation_run_id: str
    status: str
    total_rows: int
    invalid_rows: int
    batches: int
    batches_enqueued: int
    batches_skipped: int
    message: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/data/upload")
async def upload_data_file(
    analysis_run_id: str = Query(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin_or_operator),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing file name")

    # BUG-008: verify analysis_run belongs to the caller's org before associating
    _assert_analysis_run_org(db, analysis_run_id, current_user.org_id)

    # BUG-003 (path traversal): never use the client-supplied filename as a path
    safe_name = f"{uuid4()}{Path(file.filename).suffix.lower()}"
    file_path = UPLOAD_DIR / safe_name
    await save_bulk_file_with_limit(upload_file=file, destination=file_path)

    result = save_uploaded_data_file(
        db=db,
        analysis_run_id=analysis_run_id,
        file_name=file.filename,   # display name only — path uses safe_name
        file_path=file_path,
        org_id=current_user.org_id,
        created_by_user_id=current_user.id,
    )

    log_audit_event(
        db=db,
        user=current_user,
        action=AuditEvent.BULK_FILE_UPLOADED,
        resource_type="data_file",
        resource_id=result.data_file_id,
        metadata={"file_name": file.filename, "rows_count": result.rows_count},
    )

    return result.model_dump()


@router.post("/mapping/suggest")
async def suggest_mapping(
    request: MappingSuggestRequest,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin_or_operator),
):
    # BUG-007: verify both resources belong to the caller's org
    _assert_analysis_run_org(db, request.analysis_run_id, current_user.org_id)
    _assert_data_file_org(db, request.data_file_id, current_user.org_id)

    try:
        result = suggest_and_save_mappings(
            db=db,
            analysis_run_id=request.analysis_run_id,
            data_file_id=request.data_file_id,
            plan=request.plan,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    log_audit_event(
        db=db,
        user=current_user,
        action=AuditEvent.MAPPING_SUGGESTED,
        resource_type="data_file",
        resource_id=request.data_file_id,
    )

    return result


@router.post("/validate")
async def validate_bulk(
    request: BulkValidationRequest,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin_or_operator),
):
    # BUG-007: org isolation
    _assert_analysis_run_org(db, request.analysis_run_id, current_user.org_id)
    _assert_data_file_org(db, request.data_file_id, current_user.org_id)

    result = validate_bulk_data(
        db=db,
        analysis_run_id=request.analysis_run_id,
        data_file_id=request.data_file_id,
        plan=request.plan,
    )

    log_audit_event(
        db=db,
        user=current_user,
        action=AuditEvent.BULK_VALIDATED,
        resource_type="data_file",
        resource_id=request.data_file_id,
        metadata=result if isinstance(result, dict) else {},
    )

    return result


@router.post("/dry-run")
async def dry_run_bulk(
    request: BulkDryRunRequest,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin_or_operator),
):
    # BUG-007: org isolation
    _assert_data_file_org(db, request.data_file_id, current_user.org_id)

    log_audit_event(
        db=db,
        user=current_user,
        action=AuditEvent.BULK_DRY_RUN_STARTED,
        resource_type="data_file",
        resource_id=request.data_file_id,
    )

    return run_bulk_dry_run(
        db=db,
        data_file_id=request.data_file_id,
        plan=request.plan,
        allow_partial_execution=request.allow_partial_execution,
    )


@router.post(
    "/execute",
    response_model=BulkExecuteResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit(settings.RATE_LIMIT_EXECUTE)
async def execute_bulk(
    request: Request,
    body: BulkExecuteRequest,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin_or_operator),
):
    """
    Enqueue bulk execution as Celery tasks. Returns 202 immediately.
    Poll GET /jobs/{job_id}/progress for status and counts.
    """
    validate_target_url(body.base_url)

    # BUG-007: verify the data file belongs to the caller's org
    _assert_data_file_org(db, body.data_file_id, current_user.org_id)

    if not body.dry_run and current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=403,
            detail="Only admin users can run real (non-dry) bulk execution.",
        )

    # BUG-003 / FEAT-001: for real execution, require a completed validation run
    if not body.dry_run:
        validation_run = db.query(BulkValidationRun).filter(
            BulkValidationRun.data_file_id == body.data_file_id,
            BulkValidationRun.status == "completed",
        ).first()
        if not validation_run:
            raise HTTPException(
                status_code=400,
                detail="Validation must be completed before real execution. "
                       "Call POST /bulk/validate first.",
            )

    # FEAT-001: for real execution, approval_granted must be backed by a DB record
    # (client-side approval_granted=true is not sufficient on its own)
    if not body.dry_run:
        if not body.approval_granted:
            raise HTTPException(
                status_code=400,
                detail="Real execution requires approval_granted=true.",
            )
        if body.existing_automation_run_id:
            db_approval = db.query(AutomationApproval).filter(
                AutomationApproval.automation_run_id == body.existing_automation_run_id,
                AutomationApproval.status == "approved",
            ).first()
            if not db_approval:
                raise HTTPException(
                    status_code=403,
                    detail="No approved approval record found for this automation run. "
                           "An admin must approve via POST /approvals/{id}/approve.",
                )

    # BUG-001: distributed lock — prevent double-execution on the same file
    redis = get_redis()
    lock_key = f"exec_lock:{body.data_file_id}"
    acquired = redis.set(lock_key, "1", nx=True, ex=_EXEC_LOCK_TTL)
    if not acquired:
        raise HTTPException(
            status_code=409,
            detail="An execution for this data file is already in progress. "
                   "Wait for it to complete or check /jobs/{job_id}/progress.",
        )

    log_audit_event(
        db=db,
        user=current_user,
        action=AuditEvent.BULK_EXECUTION_STARTED,
        resource_type="data_file",
        resource_id=body.data_file_id,
        metadata={"dry_run": body.dry_run, "batch_size": body.batch_size},
    )

    try:
        result = await execute_valid_rows_in_batches(
            db=db,
            plan=body.plan,
            data_file_id=body.data_file_id,
            base_url=body.base_url,
            auth_headers=body.auth_headers,
            dry_run=body.dry_run,
            batch_size=body.batch_size,
            allow_partial_execution=body.allow_partial_execution,
            org_id=current_user.org_id,
            created_by_user_id=current_user.id,
            resume=body.resume,
            existing_automation_run_id=body.existing_automation_run_id,
        )
    except (ValueError, ApprovalRequiredError) as e:
        redis.delete(lock_key)   # release lock on error
        raise HTTPException(status_code=400, detail=str(e))

    # Lock released by the Celery workers when the last batch completes.
    # Safety net: TTL of 30 s ensures the lock never sticks on crash.

    return BulkExecuteResponse(
        **result,
        message=(
            f"Execution queued. Poll GET /jobs/{result['job_id']}/progress for status."
        ),
    )


@router.post("/resume", response_model=dict)
async def resume_bulk(
    request: BulkResumeRequest,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin_or_operator),
):
    """Re-enqueue incomplete batches for a previously started automation run."""
    validate_target_url(request.base_url)

    # BUG-007: verify automation_run belongs to the caller's org
    _assert_automation_run_org(db, request.automation_run_id, current_user.org_id)
    _assert_data_file_org(db, request.data_file_id, current_user.org_id)

    return resume_job(
        db=db,
        job_id=request.job_id,
        automation_run_id=request.automation_run_id,
        data_file_id=request.data_file_id,
        plan_json=request.plan.model_dump(),
        base_url=request.base_url,
        auth_headers=request.auth_headers,
        dry_run=request.dry_run,
        org_id=current_user.org_id,
    )


@router.get("/reports/{automation_run_id}")
async def get_bulk_report(
    automation_run_id: str,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin_or_operator),
):
    # BUG-007: verify ownership before returning the report
    _assert_automation_run_org(db, automation_run_id, current_user.org_id)

    try:
        return build_bulk_report(db=db, automation_run_id=automation_run_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/reports/{automation_run_id}/errors.csv")
async def download_row_errors_csv(
    automation_run_id: str,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin_or_operator),
):
    # BUG-007: verify ownership
    _assert_automation_run_org(db, automation_run_id, current_user.org_id)

    try:
        report = build_bulk_report(db=db, automation_run_id=automation_run_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["row_index", "error_code", "message"])
    for err in report["row_errors"] if isinstance(report, dict) else report.row_errors:
        # BUG-010: sanitize values to prevent CSV/spreadsheet formula injection
        row_index = err["row_index"] if isinstance(err, dict) else err.row_index
        error_code = err["error_code"] if isinstance(err, dict) else err.error_code
        message = err["message"] if isinstance(err, dict) else err.message
        writer.writerow([
            row_index,
            _sanitize_csv_cell(str(error_code or "")),
            _sanitize_csv_cell(str(message or "")),
        ])
    buf.seek(0)

    filename = f"errors_{automation_run_id[:8]}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
