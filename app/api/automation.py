import base64
from enum import Enum
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base_client import StructuredResponseError
from app.audit.service import log_audit_event
from app.auth.dependencies import require_admin_or_operator
from app.core.config import settings
from app.core.rate_limit import limiter
from app.automation.models import AutomationExecutionRequest
from app.automation.service import execute_automation
from app.db.session import get_db
from app.models.user import User, UserRole
from app.monitoring.service import log_plan_generated, log_plan_validated
from app.core.logging import get_logger
from app.planner.models import AutomationPlan
from app.planner.service import create_plan_from_instruction
from app.planner.step_ordering import DependencyCycleError, topological_sort_steps
from app.registry.repository import get_run_by_id
from app.security.execution_guard import ExecutionGuardError
from app.security.pinned_dns_transport import SSRFError
from app.security.ssrf_guard import create_safe_client, validate_target_url

router = APIRouter(prefix="/automation", tags=["Automation"])
logger = get_logger(__name__)


class CreatePlanRequest(BaseModel):
    run_id: str
    instruction: str
    top_k: int = 8


class ExecutePlanRequest(BaseModel):
    plan: AutomationPlan
    input_rows: List[Dict[str, Any]] = Field(default_factory=list)
    base_url: Optional[str] = None
    auth_headers: Dict[str, str] = Field(default_factory=dict)
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

    # BUG-007 IDOR: verify workflow belongs to the caller's org
    res = await db.execute(
        select(WorkflowModel)
        .join(AnalysisRun, AnalysisRun.id == WorkflowModel.run_id)
        .options(selectinload(WorkflowModel.steps))
        .where(
            WorkflowModel.id == body.workflow_id,
            AnalysisRun.org_id == current_user.org_id,
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

    return {"plan": plan, "validation": {"is_valid": True, "issues": []}}


@router.post("/plan")
async def create_automation_plan(
    request: Request,
    body: CreatePlanRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin_or_operator),
):
    run = await get_run_by_id(db, body.run_id)
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
    }


@router.post("/execute")
async def execute_automation_plan(
    body: ExecutePlanRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin_or_operator),
):
    if body.base_url:
        validate_target_url(body.base_url)

    if not body.dry_run and current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Only admin can run real execution.")

    if not body.dry_run and not body.approval_granted:
        raise HTTPException(status_code=403, detail="Real execution requires explicit approval.")

    execution_request = AutomationExecutionRequest(
        plan=body.plan,
        input_rows=body.input_rows,
        base_url=body.base_url,
        auth_headers=body.auth_headers,
        dry_run=body.dry_run,
    )

    try:
        automation_run, result = await execute_automation(
            db=db,
            request=execution_request,
            approval_granted=body.approval_granted,
            org_id=current_user.org_id,
            created_by_user_id=current_user.id,
        )
    except ExecutionGuardError as e:
        raise HTTPException(status_code=403, detail=str(e))

    await log_audit_event(
        db=db,
        user=current_user,
        action="AUTOMATION_EXECUTED",
        resource_type="automation_run",
        resource_id=automation_run.id,
        metadata={"dry_run": body.dry_run, "status": result.status},
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
