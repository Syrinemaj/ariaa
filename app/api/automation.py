import base64
from enum import Enum
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import log_audit_event
from app.auth.dependencies import require_admin_or_operator
from app.automation.models import AutomationExecutionRequest
from app.automation.service import execute_automation
from app.db.session import get_db
from app.models.user import User, UserRole
from app.monitoring.service import log_plan_generated, log_plan_validated
from app.planner.models import AutomationPlan
from app.planner.service import create_plan_from_instruction
from app.registry.repository import get_run_by_id
from app.security.execution_guard import ExecutionGuardError
from app.security.pinned_dns_transport import SSRFError
from app.security.ssrf_guard import create_safe_client, validate_target_url

router = APIRouter(prefix="/automation", tags=["Automation"])


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
async def validate_token(
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

    plan, validation = await create_plan_from_instruction(
        db=db,
        run_id=body.run_id,
        instruction=body.instruction,
        top_k=body.top_k,
        embedding_client=embedding_client,
        ai_client=ai_client,
        org_id=current_user.org_id,
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
