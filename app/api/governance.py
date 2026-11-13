"""Admin-only Governance Rules endpoints — risk thresholds, forbidden
endpoint rules, per-environment policy. Every mutation is written to the
audit log (who, when, what changed, see app/audit/service.py's automatic
secret redaction for the 'secret' substring, though no secret ever flows
through this router — that's Connections, app/api/connections.py)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.events import AuditEvent
from app.audit.service import log_audit_event
from app.auth.dependencies import require_admin
from app.db.session import get_db
from app.governance import service as governance_service
from app.models.governance import ForbiddenEndpointRule, GovernancePolicy
from app.models.user import User

router = APIRouter(prefix="/governance", tags=["Governance"])


def _policy_response(p: GovernancePolicy) -> dict:
    return {
        "id": p.id,
        "risk_threshold_low": p.risk_threshold_low,
        "risk_threshold_high": p.risk_threshold_high,
        "environment_policies": p.environment_policies,
        "updated_by": p.updated_by,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


def _rule_response(r: ForbiddenEndpointRule) -> dict:
    return {
        "id": r.id,
        "method": r.method,
        "path_pattern": r.path_pattern,
        "created_by": r.created_by,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


class PolicyUpdateRequest(BaseModel):
    risk_threshold_low: int | None = Field(default=None, ge=0)
    risk_threshold_high: int | None = Field(default=None, ge=0)
    environment_policies: dict[str, str] | None = None


class ForbiddenRuleCreateRequest(BaseModel):
    method: str | None = None
    path_pattern: str


@router.get("/policy", response_model=dict)
async def get_policy_route(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    policy = await governance_service.get_or_create_policy(db, current_user.org_id)
    return _policy_response(policy)


@router.patch("/policy", response_model=dict)
async def update_policy_route(
    payload: PolicyUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    try:
        policy = await governance_service.update_policy(
            db,
            org_id=current_user.org_id,
            updated_by=current_user.id,
            risk_threshold_low=payload.risk_threshold_low,
            risk_threshold_high=payload.risk_threshold_high,
            environment_policies=payload.environment_policies,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    await log_audit_event(
        db=db,
        user=current_user,
        action=AuditEvent.GOVERNANCE_POLICY_UPDATED,
        resource_type="governance_policy",
        resource_id=policy.id,
        metadata={
            "risk_threshold_low": policy.risk_threshold_low,
            "risk_threshold_high": policy.risk_threshold_high,
            "environment_policies": policy.environment_policies,
        },
    )

    return _policy_response(policy)


@router.get("/forbidden-rules", response_model=dict)
async def list_forbidden_rules_route(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    rules = await governance_service.list_forbidden_rules(db, current_user.org_id)
    return {"rules": [_rule_response(r) for r in rules]}


@router.post("/forbidden-rules", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_forbidden_rule_route(
    payload: ForbiddenRuleCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    try:
        rule = await governance_service.create_forbidden_rule(
            db,
            org_id=current_user.org_id,
            path_pattern=payload.path_pattern,
            created_by=current_user.id,
            method=payload.method,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    await log_audit_event(
        db=db,
        user=current_user,
        action=AuditEvent.GOVERNANCE_FORBIDDEN_RULE_CREATED,
        resource_type="forbidden_endpoint_rule",
        resource_id=rule.id,
        metadata={"method": rule.method, "path_pattern": rule.path_pattern},
    )

    return _rule_response(rule)


@router.delete("/forbidden-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_forbidden_rule_route(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    deleted = await governance_service.delete_forbidden_rule(db, current_user.org_id, rule_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")

    await log_audit_event(
        db=db,
        user=current_user,
        action=AuditEvent.GOVERNANCE_FORBIDDEN_RULE_DELETED,
        resource_type="forbidden_endpoint_rule",
        resource_id=rule_id,
        metadata={},
    )
