from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from pydantic import BaseModel
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
from app.db.session import get_db
from app.dry_run.service import run_bulk_dry_run
from app.mapping.service import suggest_and_save_mappings
from app.models.user import User, UserRole
from app.planner.models import AutomationPlan
from app.security.ssrf_guard import validate_target_url
from app.security.upload_limits import save_bulk_file_with_limit

router = APIRouter(prefix="/bulk", tags=["Bulk Automation"])

UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


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
    batch_size: int = settings.BULK_BATCH_SIZE
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
    batch_size: int = settings.BULK_BATCH_SIZE


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


@router.post("/data/upload")
async def upload_data_file(
    analysis_run_id: str = Query(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_operator),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing file name")

    file_path = UPLOAD_DIR / file.filename
    await save_bulk_file_with_limit(upload_file=file, destination=file_path)

    result = save_uploaded_data_file(
        db=db,
        analysis_run_id=analysis_run_id,
        file_name=file.filename,
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
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_operator),
):
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
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_operator),
):
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
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_operator),
):
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
    http_request: Request,
    request: BulkExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_operator),
):
    """
    Enqueue bulk execution as Celery tasks. Returns 202 immediately.
    Poll GET /jobs/{job_id}/progress for status and counts.

    Previously this endpoint blocked for hours on large datasets.
    Now it returns in < 500ms regardless of dataset size.
    """
    validate_target_url(request.base_url)

    if not request.dry_run and current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=403,
            detail="Only admin users can run real (non-dry) bulk execution.",
        )

    if not request.dry_run and not request.approval_granted:
        raise HTTPException(
            status_code=400,
            detail="Real execution requires approval_granted=true.",
        )

    log_audit_event(
        db=db,
        user=current_user,
        action=AuditEvent.BULK_EXECUTION_STARTED,
        resource_type="data_file",
        resource_id=request.data_file_id,
        metadata={"dry_run": request.dry_run, "batch_size": request.batch_size},
    )

    try:
        result = await execute_valid_rows_in_batches(
            db=db,
            plan=request.plan,
            data_file_id=request.data_file_id,
            base_url=request.base_url,
            auth_headers=request.auth_headers,
            dry_run=request.dry_run,
            batch_size=request.batch_size,
            allow_partial_execution=request.allow_partial_execution,
            org_id=current_user.org_id,
            created_by_user_id=current_user.id,
            resume=request.resume,
            existing_automation_run_id=request.existing_automation_run_id,
        )
    except (ValueError, ApprovalRequiredError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    return BulkExecuteResponse(
        **result,
        message=(
            f"Execution queued. Poll GET /jobs/{result['job_id']}/progress for status."
        ),
    )


@router.post("/resume", response_model=dict)
async def resume_bulk(
    request: BulkResumeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_operator),
):
    """Re-enqueue incomplete batches for a previously started automation run."""
    validate_target_url(request.base_url)

    return resume_job(
        db=db,
        job_id=request.job_id,
        automation_run_id=request.automation_run_id,
        data_file_id=request.data_file_id,
        plan_json=request.plan.model_dump(),
        base_url=request.base_url,
        auth_headers=request.auth_headers,
        dry_run=request.dry_run,
        batch_size=request.batch_size,
        org_id=current_user.org_id,
    )


@router.get("/reports/{automation_run_id}")
async def get_bulk_report(
    automation_run_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_operator),
):
    try:
        return build_bulk_report(db=db, automation_run_id=automation_run_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
