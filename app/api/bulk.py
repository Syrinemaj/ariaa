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
from app.connections import service as connection_service
from app.core.config import settings
from app.core.email import send_approval_requested_email
from app.core.rate_limit import limiter
from app.data_input.service import save_uploaded_data_file
from app.db.redis_client import get_redis
from app.db.session import AsyncSessionLocal, get_sync_db
from app.governance import service as governance_service
from app.governance.policy_engine import REQUIRE_APPROVAL, check_execution_policy
from app.dry_run.service import run_bulk_dry_run
from app.mapping.service import suggest_and_save_mappings
from app.models.analysis_run import AnalysisRun
from app.models.approval import AutomationApproval
from app.models.automation import AutomationRun
from app.models.bulk_validation import BulkValidationRun
from app.models.data_file import DataFile
from app.models.field_mapping import FieldMapping
from app.models.user import User, UserRole
from app.notifications.service import create_approval_required_notification, create_bulk_launch_notification, get_org_admins
from app.planner.models import AutomationPlan
from app.security.ssrf_guard import validate_target_url
from app.security.tenancy import owner_visibility_clause
from app.security.upload_limits import save_bulk_file_with_limit
from app.teams.service import resolve_single_team_id_sync

router = APIRouter(prefix="/bulk", tags=["Bulk Automation"])

UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Filet de sécurité uniquement — la libération réelle se fait explicitement
# dans execution.py::_update_job_progress() quand le dernier batch se termine
# (succès ou échec). Ce TTL ne sert qu'à ne pas bloquer indéfiniment si tous
# les workers meurent avant d'atteindre ce point.
_EXEC_LOCK_TTL = 6 * 3600


# ── Ownership helpers ─────────────────────────────────────────────────────────

def _assert_analysis_run_org(db: Session, analysis_run_id: str, current_user: User) -> AnalysisRun:
    """Raise 404 if the AnalysisRun doesn't exist, belongs to a different org, or
    (for an OPERATOR) wasn't created by the caller."""
    run = db.query(AnalysisRun).filter(
        AnalysisRun.id == analysis_run_id,
        AnalysisRun.org_id == current_user.org_id,
        owner_visibility_clause(AnalysisRun, current_user),
    ).first()
    if not run:
        raise HTTPException(status_code=404, detail="Analysis run not found")
    return run


async def _resolve_bulk_governance_and_approval(
    db: Session,
    plan: AutomationPlan,
    data_file: DataFile,
    connection,
    current_user: User,
    har_file_name: Optional[str],
) -> Optional[AutomationRun]:
    """
    Governance policy check + (if needed) the real admin-approval gate for a
    REAL bulk execution — assumes the caller already confirmed this isn't a
    dry run. Raises HTTPException for BLOCKED / PENDING / REJECTED; only
    returns when it's safe to proceed. Returns the existing (now-approved)
    AutomationRun to reuse, or None when no approval was required at all.

    Shared by:
      - execute_bulk: on a clean return, goes on to actually enqueue the run.
      - request_bulk_approval: only wants to get this far — to request or
        check approval status from the wizard's "Approval" step, without
        ever starting real execution, even if the answer is "approved".
    """
    async with AsyncSessionLocal() as adb:
        policy = await governance_service.get_or_create_policy(adb, current_user.org_id)
        forbidden_rules = await governance_service.list_forbidden_rules(adb, current_user.org_id)
    policy_result = check_execution_policy(plan, policy, forbidden_rules, connection.environment)

    if policy_result.is_blocked:
        # log_audit_event is async; callers here use a sync Session
        # (get_sync_db), so a separate AsyncSession is needed.
        async with AsyncSessionLocal() as adb:
            await log_audit_event(
                db=adb,
                user=current_user,
                action=AuditEvent.AUTOMATION_GOVERNANCE_BLOCKED,
                resource_type="data_file",
                resource_id=data_file.id,
                metadata={"reasons": policy_result.reasons, "risk_score": policy_result.risk_score},
            )
            await adb.commit()
        raise HTTPException(
            status_code=403,
            detail={
                "code": "GOVERNANCE_BLOCKED",
                "message": "This execution is blocked by governance policy.",
                "reasons": policy_result.reasons,
            },
        )

    # Bulk is higher blast-radius than a single Simple Automation action (one
    # approval covers N rows at once) — unlike Simple Automation's
    # governance-conditional exemption, an OPERATOR always needs admin
    # sign-off for a real bulk run, regardless of the policy's own risk
    # decision. Governance can still make it WORSE (REQUIRE_APPROVAL/BLOCK
    # apply to admins too) but never better than "operator needs approval"
    # for a non-admin.
    needs_approval = policy_result.decision == REQUIRE_APPROVAL or current_user.role != UserRole.ADMIN
    if not needs_approval:
        return None

    # Mirrors Simple Automation's real approval flow (app/api/automation.py)
    # instead of trusting a client-sent approval_granted=true. First call for
    # a given data_file+user creates a pending AutomationRun +
    # AutomationApproval and 403s with its id; the frontend polls GET
    # /approvals for the decision; once an admin approves, retrying finds
    # that record and proceeds.
    pending = db.query(AutomationRun, AutomationApproval).join(
        AutomationApproval, AutomationApproval.automation_run_id == AutomationRun.id
    ).filter(
        AutomationRun.analysis_run_id == data_file.analysis_run_id,
        AutomationRun.created_by_user_id == current_user.id,
        AutomationRun.status == "pending_approval",
        AutomationRun.plan_json["_bulk_data_file_id"].astext == data_file.id,
    ).order_by(AutomationRun.created_at.desc()).first()

    if pending is None:
        pending_run = AutomationRun(
            analysis_run_id=data_file.analysis_run_id,
            instruction=f"Bulk execution: {har_file_name or data_file.id}",
            workflow_name=plan.workflow_name,
            dry_run=False,
            source="bulk",
            status="pending_approval",
            total_steps=len(plan.steps),
            plan_json={**plan.model_dump(), "_bulk_data_file_id": data_file.id},
            org_id=current_user.org_id,
            created_by_user_id=current_user.id,
            team_id=resolve_single_team_id_sync(db, current_user.id),
            connection_id=connection.id,
        )
        db.add(pending_run)
        db.flush()
        db.add(AutomationApproval(automation_run_id=pending_run.id, status="pending"))
        create_approval_required_notification(
            db=db,
            requester=current_user,
            resource_type="automation_run",
            resource_id=pending_run.id,
            har_file_name=har_file_name,
        )
        # Commit now — we're about to raise, and get_sync_db() rolls back
        # the session on exception, which would otherwise drop all of this.
        db.commit()
        await _email_admins_approval_requested(db, current_user.org_id, current_user, har_file_name or "a bulk execution")
        raise HTTPException(
            status_code=403,
            detail={
                "code": "APPROVAL_PENDING",
                "message": "Real execution requires admin approval — a request has been sent.",
                "automation_run_id": pending_run.id,
            },
        )

    run, approval = pending
    if approval.status == "rejected":
        raise HTTPException(
            status_code=403,
            detail={
                "code": "APPROVAL_REJECTED",
                "message": "Your approval request was rejected"
                + (f": {approval.comment}" if approval.comment else "."),
            },
        )
    if approval.status != "approved":
        raise HTTPException(
            status_code=403,
            detail={
                "code": "APPROVAL_PENDING",
                "message": "Still waiting on admin approval for this run.",
                "automation_run_id": run.id,
            },
        )

    # A real admin approved this exact pending run — safe to trust now.
    return run


async def _email_admins_approval_requested(db: Session, org_id: str, operator: User, resource_label: str) -> None:
    # execute_bulk is `async def` (unlike app/api/approvals.py's plain `def`
    # routes) — it already runs on a live event loop, so run_email_coro_sync's
    # asyncio.run() would raise "cannot be called from a running event loop".
    # Await directly instead; this is a real pre-existing bug this fix
    # surfaced, not something introduced by governance wiring — it was
    # simply unreachable for operators before (they couldn't request real
    # bulk execution at all) and rare for admins (self-attested
    # approval_granted=False on purpose).
    for admin in get_org_admins(db, org_id):
        await send_approval_requested_email(
            to=admin.email,
            admin_name=admin.full_name,
            operator_name=operator.full_name,
            resource_label=resource_label,
            approvals_link=f"{settings.FRONTEND_URL}/approvals",
        )


def _assert_data_file_org(db: Session, data_file_id: str, org_id: str) -> DataFile:
    """Raise 404 if the DataFile doesn't exist or belongs to a different org."""
    df = db.query(DataFile).filter(
        DataFile.id == data_file_id,
        DataFile.org_id == org_id,
    ).first()
    if not df:
        raise HTTPException(status_code=404, detail="Data file not found")
    return df


def _assert_automation_run_org(db: Session, automation_run_id: str, current_user: User) -> AutomationRun:
    """Raise 404 if the AutomationRun doesn't exist, belongs to a different org, or
    (for an OPERATOR) wasn't created by the caller."""
    run = db.query(AutomationRun).filter(
        AutomationRun.id == automation_run_id,
        AutomationRun.org_id == current_user.org_id,
        owner_visibility_clause(AutomationRun, current_user),
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


class MappingApproveRequest(BaseModel):
    approved: bool = True


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
    connection_id: str
    dry_run: bool = True
    # BUG-013: constrain batch_size to avoid divide-by-zero and runaway jobs
    batch_size: int = Field(default=settings.BULK_BATCH_SIZE, ge=1, le=500)
    allow_partial_execution: bool = True
    approval_granted: bool = False
    resume: bool = False
    existing_automation_run_id: Optional[str] = None


class BulkApprovalCheckRequest(BaseModel):
    plan: AutomationPlan
    data_file_id: str
    connection_id: str


class BulkResumeRequest(BaseModel):
    job_id: str
    automation_run_id: str
    data_file_id: str
    plan: AutomationPlan
    connection_id: str
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
    _assert_analysis_run_org(db, analysis_run_id, current_user)

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

    # log_audit_event is async and needs an AsyncSession — this route uses a
    # sync Session (get_sync_db); a bare, un-awaited call here silently
    # built a coroutine that was never run (RuntimeWarning, no audit row
    # ever written). Same bug fixed across every call site in this file.
    async with AsyncSessionLocal() as adb:
        await log_audit_event(
            db=adb,
            user=current_user,
            action=AuditEvent.BULK_FILE_UPLOADED,
            resource_type="data_file",
            resource_id=result.data_file_id,
            metadata={"file_name": file.filename, "rows_count": result.rows_count},
        )
        await adb.commit()

    return result.model_dump()


@router.post("/mapping/suggest")
async def suggest_mapping(
    request: MappingSuggestRequest,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin_or_operator),
):
    # BUG-007: verify both resources belong to the caller's org
    _assert_analysis_run_org(db, request.analysis_run_id, current_user)
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

    async with AsyncSessionLocal() as adb:
        await log_audit_event(
            db=adb,
            user=current_user,
            action=AuditEvent.MAPPING_SUGGESTED,
            resource_type="data_file",
            resource_id=request.data_file_id,
        )
        await adb.commit()

    return result


@router.patch("/mapping/{mapping_id}/approve")
async def approve_mapping(
    mapping_id: str,
    body: MappingApproveRequest,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin_or_operator),
):
    """Manually approve (or revoke) a field mapping suggestion that fell below
    the auto-approve confidence bar — e.g. a synonym/fuzzy match. Only approved
    mappings are used by /bulk/validate and /bulk/execute, so a suggestion the
    system found but didn't trust enough to auto-approve is otherwise a dead
    end without this."""
    field_mapping = db.query(FieldMapping).filter(FieldMapping.id == mapping_id).first()
    if not field_mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")

    # BUG-007: verify the mapping's analysis_run belongs to the caller's org
    _assert_analysis_run_org(db, field_mapping.analysis_run_id, current_user)

    field_mapping.approved = body.approved
    db.commit()

    return {
        "id": field_mapping.id,
        "source_field": field_mapping.source_field,
        "target_field": field_mapping.target_field,
        "approved": field_mapping.approved,
    }


@router.post("/validate")
async def validate_bulk(
    request: BulkValidationRequest,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin_or_operator),
):
    # BUG-007: org isolation
    _assert_analysis_run_org(db, request.analysis_run_id, current_user)
    _assert_data_file_org(db, request.data_file_id, current_user.org_id)

    result = validate_bulk_data(
        db=db,
        analysis_run_id=request.analysis_run_id,
        data_file_id=request.data_file_id,
        plan=request.plan,
    )

    async with AsyncSessionLocal() as adb:
        await log_audit_event(
            db=adb,
            user=current_user,
            action=AuditEvent.BULK_VALIDATED,
            resource_type="data_file",
            resource_id=request.data_file_id,
            metadata=result if isinstance(result, dict) else {},
        )
        await adb.commit()

    return result


@router.post("/dry-run")
async def dry_run_bulk(
    request: BulkDryRunRequest,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin_or_operator),
):
    # BUG-007: org isolation
    _assert_data_file_org(db, request.data_file_id, current_user.org_id)

    async with AsyncSessionLocal() as adb:
        await log_audit_event(
            db=adb,
            user=current_user,
            action=AuditEvent.BULK_DRY_RUN_STARTED,
            resource_type="data_file",
            resource_id=request.data_file_id,
        )
        await adb.commit()

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
    async with AsyncSessionLocal() as adb:
        connection = await connection_service.get_connection(adb, current_user.org_id, body.connection_id)
        if connection is None:
            raise HTTPException(status_code=404, detail="Connection not found")
        if not await connection_service.user_can_use_connection(adb, connection, current_user):
            raise HTTPException(
                status_code=403,
                detail="You are not assigned to this connection" if connection.status == "active"
                else "This connection has been revoked",
            )

    validate_target_url(connection.base_url)

    # BUG-007: verify the data file belongs to the caller's org
    data_file = _assert_data_file_org(db, body.data_file_id, current_user.org_id)
    analysis_run = db.query(AnalysisRun).filter(AnalysisRun.id == data_file.analysis_run_id).first()
    har_file_name = analysis_run.file_name if analysis_run else None

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

    # Governance check (Feature 1) — replaces the old hardcoded "operators
    # can never run real bulk execution" rule — plus, if needed, the real
    # admin-approval gate. Runs on every real-execution call (serves as "at
    # submission"); the Celery worker re-runs governance again right before
    # the actual HTTP calls fire (see _run_batch_async in
    # app/workers/tasks/execution.py), since a batch may not actually
    # execute until long after this request returns.
    # Shared with POST /bulk/request-approval, which calls the exact same
    # helper but stops here — it never reaches the execution below, even
    # when the answer is "approved": requesting/checking approval from the
    # wizard's Approval step must never itself trigger a real run.
    existing_run: Optional[AutomationRun] = None
    if not body.dry_run:
        existing_run = await _resolve_bulk_governance_and_approval(
            db=db, plan=body.plan, data_file=data_file, connection=connection,
            current_user=current_user, har_file_name=har_file_name,
        )
        if existing_run is not None:
            body.existing_automation_run_id = existing_run.id

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

    async with AsyncSessionLocal() as adb:
        await log_audit_event(
            db=adb,
            user=current_user,
            action=AuditEvent.BULK_EXECUTION_STARTED,
            resource_type="data_file",
            resource_id=body.data_file_id,
            metadata={"dry_run": body.dry_run, "batch_size": body.batch_size},
        )
        await adb.commit()

    # Notify the admins of the operator's org ("team") that a bulk run just launched.
    if current_user.role == UserRole.OPERATOR:
        create_bulk_launch_notification(
            db=db,
            operator=current_user,
            resource_id=body.data_file_id,
            har_file_name=har_file_name,
        )

    try:
        result = await execute_valid_rows_in_batches(
            db=db,
            plan=body.plan,
            data_file_id=body.data_file_id,
            connection_id=connection.id,
            dry_run=body.dry_run,
            batch_size=body.batch_size,
            allow_partial_execution=body.allow_partial_execution,
            org_id=current_user.org_id,
            created_by_user_id=current_user.id,
            team_id=resolve_single_team_id_sync(db, current_user.id),
            resume=body.resume,
            existing_automation_run_id=body.existing_automation_run_id,
            har_file_name=har_file_name,
        )
    except (ValueError, ApprovalRequiredError) as e:
        redis.delete(lock_key)   # release lock on error
        raise HTTPException(status_code=400, detail=str(e))

    # Lock released explicitly by execution.py::_update_job_progress() when
    # the last batch reports in. _EXEC_LOCK_TTL above is only a safety net
    # for the case where every worker crashes before reaching that point.

    return BulkExecuteResponse(
        **result,
        message=(
            f"Execution queued. Poll GET /jobs/{result['job_id']}/progress for status."
        ),
    )


@router.post("/request-approval")
async def request_bulk_approval(
    body: BulkApprovalCheckRequest,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin_or_operator),
):
    """
    Governance/approval check ONLY — reuses the exact same decision logic as
    POST /bulk/execute (_resolve_bulk_governance_and_approval) but never
    enqueues anything, even when the answer turns out to be "approved".

    Lets the wizard's Approval step (BulkPage.tsx) show real admin-approval
    status up front — request it, poll GET /approvals, see it turn green —
    while execution itself stays a separate, deliberate click on the
    Execute step, same as Simple Automation's "Execute for real".
    """
    async with AsyncSessionLocal() as adb:
        connection = await connection_service.get_connection(adb, current_user.org_id, body.connection_id)
        if connection is None:
            raise HTTPException(status_code=404, detail="Connection not found")
        if not await connection_service.user_can_use_connection(adb, connection, current_user):
            raise HTTPException(
                status_code=403,
                detail="You are not assigned to this connection" if connection.status == "active"
                else "This connection has been revoked",
            )

    validate_target_url(connection.base_url)

    data_file = _assert_data_file_org(db, body.data_file_id, current_user.org_id)
    analysis_run = db.query(AnalysisRun).filter(AnalysisRun.id == data_file.analysis_run_id).first()
    har_file_name = analysis_run.file_name if analysis_run else None

    existing_run = await _resolve_bulk_governance_and_approval(
        db=db, plan=body.plan, data_file=data_file, connection=connection,
        current_user=current_user, har_file_name=har_file_name,
    )
    return {
        "code": "APPROVED" if existing_run is not None else "NOT_REQUIRED",
        "message": (
            "Approved — you can execute for real."
            if existing_run is not None
            else "No admin approval required for this run."
        ),
        "automation_run_id": existing_run.id if existing_run else None,
    }


@router.post("/resume", response_model=dict)
async def resume_bulk(
    request: BulkResumeRequest,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin_or_operator),
):
    """Re-enqueue incomplete batches for a previously started automation run."""
    async with AsyncSessionLocal() as adb:
        connection = await connection_service.get_connection(adb, current_user.org_id, request.connection_id)
        if connection is None:
            raise HTTPException(status_code=404, detail="Connection not found")
        if not await connection_service.user_can_use_connection(adb, connection, current_user):
            raise HTTPException(
                status_code=403,
                detail="You are not assigned to this connection" if connection.status == "active"
                else "This connection has been revoked",
            )

    validate_target_url(connection.base_url)

    # BUG-007: verify automation_run belongs to the caller's org
    _assert_automation_run_org(db, request.automation_run_id, current_user)
    _assert_data_file_org(db, request.data_file_id, current_user.org_id)

    return resume_job(
        db=db,
        job_id=request.job_id,
        automation_run_id=request.automation_run_id,
        data_file_id=request.data_file_id,
        plan_json=request.plan.model_dump(),
        connection_id=connection.id,
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
    _assert_automation_run_org(db, automation_run_id, current_user)

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
    _assert_automation_run_org(db, automation_run_id, current_user)

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
