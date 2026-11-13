import base64
from enum import Enum
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base_client import StructuredResponseError
from app.audit.events import AuditEvent
from app.audit.service import log_audit_event
from app.auth.dependencies import require_admin_or_operator
from app.connections import service as connection_service
from app.core.config import settings
from app.core.rate_limit import limiter
from app.automation.models import AutomationExecutionRequest
from app.automation.payload_mapper import required_input_fields
from app.automation.service import execute_automation
from app.db.session import get_db
from app.governance import service as governance_service
from app.governance.policy_engine import REQUIRE_APPROVAL, check_execution_policy
from app.models.analysis_run import AnalysisRun
from app.models.approval import AutomationApproval
from app.models.automation import AutomationRun
from app.models.user import User, UserRole
from app.monitoring.service import log_plan_generated, log_plan_validated
from app.core.email import send_approval_requested_email
from app.notifications.service import create_approval_required_notification_async, get_org_admins_async
from app.core.logging import get_logger
from app.planner.models import AutomationPlan
from app.planner.plan_validator import check_action_coherence
from app.planner.service import create_plan_from_instruction
from app.planner.step_ordering import DependencyCycleError, topological_sort_steps
from app.registry.repository import get_run_by_id
from app.security.execution_guard import ExecutionGuardError
from app.security.pinned_dns_transport import SSRFError
from app.security.ssrf_guard import create_safe_client, validate_target_url
from app.security.tenancy import owner_visibility_clause
from app.teams.service import resolve_single_team_id

router = APIRouter(prefix="/automation", tags=["Automation"])
logger = get_logger(__name__)


class CreatePlanRequest(BaseModel):
    run_id: str
    instruction: str
    top_k: int = 8


class ExecutePlanRequest(BaseModel):
    plan: AutomationPlan
    input_rows: List[Dict[str, Any]] = Field(default_factory=list)
    connection_id: str
    dry_run: bool = True
    approval_granted: bool = False


class TokenType(str, Enum):
    bearer = "bearer"
    api_key = "api_key"
    basic = "basic"


class ValidateTokenRequest(BaseModel):
    base_url: str
    token_type: TokenType
    token_value: str
    header_name: Optional[str] = None   # api_key only — defaults to "X-Api-Key"
    username: Optional[str] = None      # basic only
    probe_path: str = "/"

    @field_validator("token_value")
    @classmethod
    def token_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("TOKEN_EMPTY")
        return v.strip()

    @field_validator("base_url")
    @classmethod
    def base_url_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("base_url is required")
        return v.strip().rstrip("/")


class ValidateTokenResponse(BaseModel):
    valid: bool
    error_code: Optional[str] = None
    message: str
    status_code: Optional[int] = None


def _build_auth_headers(req: ValidateTokenRequest) -> Dict[str, str]:
    if req.token_type == TokenType.bearer:
        return {"Authorization": f"Bearer {req.token_value}"}
    if req.token_type == TokenType.api_key:
        name = (req.header_name or "X-Api-Key").strip()
        return {name: req.token_value}
    if req.token_type == TokenType.basic:
        username = (req.username or "").strip()
        credentials = base64.b64encode(
            f"{username}:{req.token_value}".encode()
        ).decode()
        return {"Authorization": f"Basic {credentials}"}
    return {}


@router.post("/validate-token", response_model=ValidateTokenResponse)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def validate_token(
    request: Request,
    body: ValidateTokenRequest,
    current_user: User = Depends(require_admin_or_operator),
) -> ValidateTokenResponse:
    """
    Probe the target API with the supplied token.
    Returns a typed error_code so the frontend can show a precise message.
    """
    # Basic format sanity: Bearer tokens that look like JWTs must have 3 segments
    if body.token_type == TokenType.bearer:
        parts = body.token_value.split(".")
        if len(parts) == 2 or (len(parts) > 1 and not all(parts)):
            return ValidateTokenResponse(
                valid=False,
                error_code="TOKEN_MALFORMED",
                message="Token format invalid — expected a valid Bearer token (e.g. eyJ…)",
            )

    auth_headers = _build_auth_headers(body)
    probe_url = f"{body.base_url}/{body.probe_path.lstrip('/')}"

    try:
        async with create_safe_client(
            base_url=body.base_url,
            timeout=httpx.Timeout(connect=8.0, read=10.0, write=10.0, pool=5.0),
        ) as client:
            response = await client.get(probe_url, headers=auth_headers)
    except SSRFError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.TimeoutException):
        return ValidateTokenResponse(
            valid=False,
            error_code="API_UNREACHABLE",
            message="Cannot reach the API — check your network or the API base URL",
        )
    except Exception as exc:
        return ValidateTokenResponse(
            valid=False,
            error_code="API_UNREACHABLE",
            message=f"Cannot reach the API — {exc}",
        )

    if response.status_code == 401:
        return ValidateTokenResponse(
            valid=False,
            error_code="TOKEN_EXPIRED",
            message="Token expired — please generate a new token and try again",
            status_code=401,
        )
    if response.status_code == 403:
        return ValidateTokenResponse(
            valid=False,
            error_code="TOKEN_INVALID",
            message="Invalid token — check that you copied the full token without extra spaces",
            status_code=403,
        )
    if response.status_code >= 400:
        return ValidateTokenResponse(
            valid=False,
            error_code="UNKNOWN_ERROR",
            message=f"API returned an unexpected error (HTTP {response.status_code})",
            status_code=response.status_code,
        )

    return ValidateTokenResponse(
        valid=True,
        error_code=None,
        message="Token validated successfully",
        status_code=response.status_code,
    )


class PlanFromWorkflowRequest(BaseModel):
    workflow_id: str


@router.post("/plan-from-workflow")
async def plan_from_workflow(
    body: PlanFromWorkflowRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin_or_operator),
):
    """
    Convert an existing WorkflowModel directly into an AutomationPlan without an LLM call.
    Each step is enriched with the corresponding Endpoint's schema (request/response schemas,
    auth requirements, risk level).
    """
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.models.analysis_run import AnalysisRun
    from app.models.workflow import WorkflowModel
    from app.models.endpoint import Endpoint

    # BUG-007 IDOR: verify workflow belongs to the caller's org (+ ownership scoping)
    res = await db.execute(
        select(WorkflowModel)
        .join(AnalysisRun, AnalysisRun.id == WorkflowModel.run_id)
        .options(selectinload(WorkflowModel.steps))
        .where(
            WorkflowModel.id == body.workflow_id,
            AnalysisRun.org_id == current_user.org_id,
            owner_visibility_clause(AnalysisRun, current_user),
        )
    )
    wf = res.scalar_one_or_none()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")

    ep_res = await db.execute(
        select(Endpoint)
        .options(selectinload(Endpoint.schema))
        .where(Endpoint.run_id == wf.run_id)
    )
    ep_by_canonical: dict = {ep.canonical_key: ep for ep in ep_res.scalars().all()}

    steps = []
    for s in sorted(wf.steps, key=lambda x: x.step_order):
        ep = ep_by_canonical.get(s.canonical_key)
        schema = ep.schema if ep else None
        steps.append({
            "order": s.step_order,
            "endpoint_id": ep.id if ep else s.canonical_key,
            "method": s.method,
            "path": s.path,
            "canonical_key": s.canonical_key,
            "action": s.action or "",
            "business_domain": ep.business_domain if ep else "",
            "depends_on": s.depends_on or [],
            "request_schema": schema.request_schema or {} if schema else {},
            "response_schema": schema.response_schema or {} if schema else {},
            "auth_required": schema.auth_required if schema else True,
            "risk_level": (ep.metadata_json or {}).get("risk", "low") if ep else "low",
        })

    # depends_on comes straight from detected workflow data (usually already
    # a valid chronological order), but re-sort defensively — schema-based
    # dependency detection (Pass 2 in dependency_detector.py) can in rare
    # cases point at a step that comes later in raw step_order.
    try:
        steps = topological_sort_steps(steps)
    except DependencyCycleError as exc:
        logger.warning(
            "plan_from_workflow.dependency_cycle", workflow_id=wf.id, error=str(exc)
        )

    plan = {
        "run_id": wf.run_id,
        "instruction": f"Exécuter le workflow {wf.name}",
        "intent": {
            "instruction": f"Exécuter le workflow {wf.name}",
            "intent": wf.business_domain or "automation",
            "business_domain": wf.business_domain or "",
            "quantity": None,
            "entities": [],
            "action": "execute",
            "confidence": wf.confidence or 0.9,
            "requires_bulk_execution": True,
            "reason": f"Conversion directe depuis WorkflowModel {wf.id}",
        },
        "workflow_name": wf.name,
        "steps": steps,
        "requires_approval": True,
        "dry_run_default": True,
        "metadata": {"source": "workflow", "workflow_id": wf.id},
    }

    return {
        "plan": plan,
        "validation": {"is_valid": True, "issues": []},
        "required_input_fields": required_input_fields(AutomationPlan.model_validate(plan)),
    }


@router.post("/plan")
async def create_automation_plan(
    request: Request,
    body: CreatePlanRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin_or_operator),
):
    run = await get_run_by_id(db, body.run_id, current_user.org_id)
    if not run:
        raise HTTPException(status_code=404, detail="Analysis run not found")

    ai_client = request.app.state.ai_client
    embedding_client = request.app.state.embedding_client

    try:
        plan, validation = await create_plan_from_instruction(
            db=db,
            run_id=body.run_id,
            instruction=body.instruction,
            top_k=body.top_k,
            embedding_client=embedding_client,
            ai_client=ai_client,
            org_id=current_user.org_id,
        )
    except StructuredResponseError:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "LLM_RESPONSE_INVALID",
                "message": "Le modèle IA n'a pas retourné de réponse exploitable pour cette instruction.",
                "suggestion": "Réessayez, ou reformulez l'instruction différemment.",
            },
        )

    # Confidence gate applies regardless of whether RAG found any endpoints —
    # semantic search always returns its "closest" matches, so a low-confidence
    # (unclear/nonsense) instruction can accidentally match something and slip
    # past an empty-steps-only check. This must run first.
    confidence = plan.intent.confidence if plan.intent else 0.0
    reason = (plan.intent.reason or "").upper() if plan.intent else ""
    if confidence < settings.PLAN_MIN_INTENT_CONFIDENCE or "UNCLEAR" in reason:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INSTRUCTION_UNCLEAR",
                "message": "L'instruction est trop vague ou ne décrit pas une action API concrète.",
                "suggestion": "Exemple : « Créer un employé avec contrat CDI et envoyer un email de bienvenue »",
                "confidence": confidence,
            },
        )

    if not plan.steps:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "NO_MATCHING_ENDPOINTS",
                "message": "Aucun endpoint correspondant n'a été trouvé dans ce run d'analyse.",
                "suggestion": "Vérifiez que le run contient les APIs nécessaires, ou reformulez l'instruction.",
                "confidence": confidence,
            },
        )

    coherence_issue = check_action_coherence(plan)
    if coherence_issue:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "ACTION_NOT_AVAILABLE",
                "message": (
                    f"Aucun endpoint du catalogue ne permet l'action demandée "
                    f"(« {plan.intent.action} »). Le plan proposé réaliserait une autre action."
                ),
                "suggestion": "Vérifiez que le trafic analysé contient un appel réalisant cette action.",
                "confidence": confidence,
            },
        )

    log_plan_generated(
        run_id=body.run_id,
        instruction=body.instruction,
        steps_count=len(plan.steps),
    )
    log_plan_validated(is_valid=validation.is_valid, issues_count=len(validation.issues))

    await log_audit_event(
        db=db,
        user=current_user,
        action="AUTOMATION_PLAN_GENERATED",
        resource_type="analysis_run",
        resource_id=body.run_id,
        metadata={"instruction": body.instruction, "top_k": body.top_k},
    )

    return {
        "plan": plan.model_dump(),
        "validation": validation.model_dump(),
        "required_input_fields": required_input_fields(plan),
    }


@router.post("/execute")
async def execute_automation_plan(
    body: ExecutePlanRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin_or_operator),
):
    connection = await connection_service.get_connection(db, current_user.org_id, body.connection_id)
    if connection is None:
        raise HTTPException(status_code=404, detail="Connection not found")
    if not await connection_service.user_can_use_connection(db, connection, current_user):
        raise HTTPException(
            status_code=403,
            detail="You are not assigned to this connection" if connection.status == "active"
            else "This connection has been revoked",
        )

    validate_target_url(connection.base_url)

    existing_run: Optional[AutomationRun] = None
    approval_granted = body.approval_granted

    if not body.dry_run:
        # Governance check (Feature 1) — runs on EVERY non-dry-run call, both
        # the operator's first request (serves as "at submission") and any
        # retry after admin approval (serves as "again just before
        # execution": policy may have changed in the meantime). A BLOCK is
        # terminal regardless of role — it is checked before the
        # admin/operator branch below, so admin approval can never override
        # it (see app/governance/policy_engine.py docstring).
        policy = await governance_service.get_or_create_policy(db, current_user.org_id)
        forbidden_rules = await governance_service.list_forbidden_rules(db, current_user.org_id)
        policy_result = check_execution_policy(body.plan, policy, forbidden_rules, connection.environment)

        if policy_result.is_blocked:
            await log_audit_event(
                db=db,
                user=current_user,
                action=AuditEvent.AUTOMATION_GOVERNANCE_BLOCKED,
                resource_type="analysis_run",
                resource_id=body.plan.run_id,
                metadata={"reasons": policy_result.reasons, "risk_score": policy_result.risk_score},
            )
            # Commit now — we're about to raise, and get_db() rolls back the
            # session on exception, which would otherwise drop this entry
            # (same gotcha as the pending-approval path below).
            await db.commit()
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "GOVERNANCE_BLOCKED",
                    "message": "This execution is blocked by governance policy.",
                    "reasons": policy_result.reasons,
                },
            )

        if current_user.role != UserRole.ADMIN and policy_result.decision != REQUIRE_APPROVAL:
            # ALLOW: risk is below the low threshold and the environment
            # permits it — the operator executes directly (Feature 1's
            # whole point). approval_granted=True here satisfies the older,
            # narrower app/security/execution_guard.py check further down
            # (which gates on HTTP method alone) — governance has already
            # made the real decision.
            approval_granted = True

    if not body.dry_run and current_user.role != UserRole.ADMIN and policy_result.decision == REQUIRE_APPROVAL:
        # OPERATOR requesting a REAL run that governance says needs admin
        # sign-off: no self-checked "Approved" box is trusted here — needs
        # an admin to have actually approved THIS plan via
        # POST /approvals/{id}/approve first (verified against a real
        # AutomationApproval row, not the client-sent boolean). First request
        # for a given plan creates a pending run + approval and notifies
        # every admin in the org; the operator retries the same call once
        # approved (or gets a clear rejection message if refused).
        from sqlalchemy import select

        pending = await db.execute(
            select(AutomationRun, AutomationApproval)
            .join(AutomationApproval, AutomationApproval.automation_run_id == AutomationRun.id)
            .where(
                AutomationRun.analysis_run_id == body.plan.run_id,
                AutomationRun.created_by_user_id == current_user.id,
                AutomationRun.status == "pending_approval",
            )
            .order_by(AutomationRun.created_at.desc())
        )
        row = pending.first()

        if row is None:
            pending_run = AutomationRun(
                analysis_run_id=body.plan.run_id,
                instruction=body.plan.instruction,
                workflow_name=body.plan.workflow_name,
                dry_run=False,
                source="simple",
                status="pending_approval",
                total_steps=len(body.plan.steps),
                plan_json=body.plan.model_dump(),
                org_id=current_user.org_id,
                created_by_user_id=current_user.id,
                team_id=await resolve_single_team_id(db, current_user.id),
                connection_id=connection.id,
            )
            db.add(pending_run)
            await db.flush()
            db.add(AutomationApproval(automation_run_id=pending_run.id, status="pending"))

            analysis_run_result = await db.execute(
                select(AnalysisRun).where(AnalysisRun.id == body.plan.run_id)
            )
            analysis_run = analysis_run_result.scalar_one_or_none()
            await create_approval_required_notification_async(
                db=db,
                requester=current_user,
                resource_type="automation_run",
                resource_id=pending_run.id,
                har_file_name=analysis_run.file_name if analysis_run else None,
            )
            # Commit now — we're about to raise, and get_db() rolls back the
            # session on exception, which would otherwise drop all of this.
            await db.commit()

            resource_label = analysis_run.file_name if analysis_run else body.plan.workflow_name
            admins = await get_org_admins_async(db, current_user.org_id)
            for admin in admins:
                await send_approval_requested_email(
                    to=admin.email,
                    admin_name=admin.full_name,
                    operator_name=current_user.full_name,
                    resource_label=resource_label,
                    approvals_link=f"{settings.FRONTEND_URL}/approvals",
                )

            raise HTTPException(
                status_code=403,
                detail={
                    "code": "APPROVAL_PENDING",
                    "message": "Real execution requires admin approval — a request has been sent.",
                    "automation_run_id": pending_run.id,
                },
            )

        run, approval = row
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
        existing_run = run
        approval_granted = True

    # dry_run never calls the target or needs the secret (execute_step
    # returns before any network I/O — see app/automation/executor.py) but
    # still needs base_url to resolve+show the preview URL. Only decrypt
    # for a real run.
    auth_headers: Dict[str, str] = {}
    if not body.dry_run:
        secret = connection_service.get_decrypted_secret_for_execution(connection)
        auth_headers = connection_service.build_auth_headers(connection.auth_type, secret)

    execution_request = AutomationExecutionRequest(
        plan=body.plan,
        input_rows=body.input_rows,
        base_url=connection.base_url,
        auth_headers=auth_headers,
        connection_id=connection.id,
        dry_run=body.dry_run,
    )

    try:
        automation_run, result = await execute_automation(
            db=db,
            request=execution_request,
            approval_granted=approval_granted,
            org_id=current_user.org_id,
            created_by_user_id=current_user.id,
            team_id=await resolve_single_team_id(db, current_user.id),
            existing_run=existing_run,
        )
    except ExecutionGuardError as e:
        raise HTTPException(status_code=403, detail=str(e))

    await log_audit_event(
        db=db,
        user=current_user,
        action="AUTOMATION_EXECUTED",
        resource_type="automation_run",
        resource_id=automation_run.id,
        metadata={"dry_run": body.dry_run, "status": result.status, "connection_id": connection.id},
    )

    return {
        "automation_run_id": automation_run.id,
        "status": result.status,
        "dry_run": result.dry_run,
        "success_count": result.success_count,
        "failed_count": result.failed_count,
        "total_steps": result.total_steps,
        "result": result.model_dump(),
    }
