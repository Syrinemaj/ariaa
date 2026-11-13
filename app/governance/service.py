"""Governance service — async SQLAlchemy (AsyncSession), mirrors
app/teams/service.py.

Audit logging for mutations happens in the API route layer (app/api/governance.py),
not here — same split as teams/users (see app/api/teams.py), so this module
stays a plain, directly-testable CRUD layer.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.governance import DEFAULT_ENVIRONMENT_POLICIES, ForbiddenEndpointRule, GovernancePolicy

VALID_ENVIRONMENTS = {"test", "preprod", "prod"}
VALID_ENVIRONMENT_MODES = {"full_access", "writes_require_approval", "read_only", "forbidden"}


def _policy_dict(p: GovernancePolicy) -> dict:
    return {
        "id": p.id,
        "org_id": p.org_id,
        "risk_threshold_low": p.risk_threshold_low,
        "risk_threshold_high": p.risk_threshold_high,
        "environment_policies": p.environment_policies,
        "updated_by": p.updated_by,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


def _rule_dict(r: ForbiddenEndpointRule) -> dict:
    return {
        "id": r.id,
        "org_id": r.org_id,
        "method": r.method,
        "path_pattern": r.path_pattern,
        "created_by": r.created_by,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _validate_environment_policies(environment_policies: dict) -> None:
    unknown_envs = set(environment_policies) - VALID_ENVIRONMENTS
    if unknown_envs:
        raise ValueError(f"Unknown environment(s): {', '.join(sorted(unknown_envs))}")

    invalid_modes = {
        env: mode for env, mode in environment_policies.items() if mode not in VALID_ENVIRONMENT_MODES
    }
    if invalid_modes:
        raise ValueError(
            f"Invalid environment policy mode(s): {invalid_modes} — "
            f"must be one of {sorted(VALID_ENVIRONMENT_MODES)}"
        )


async def get_or_create_policy(db: AsyncSession, org_id: str) -> GovernancePolicy:
    """Every org has exactly one GovernancePolicy row. It's created lazily
    (rather than at org-creation time) so orgs that predate this feature
    pick up the default-permissive policy the first time it's read —
    reproducing pre-governance behavior (see app/governance/policy_engine.py
    docstring) until an admin explicitly tightens it."""
    result = await db.execute(select(GovernancePolicy).where(GovernancePolicy.org_id == org_id))
    policy = result.scalar_one_or_none()
    if policy is not None:
        return policy

    policy = GovernancePolicy(org_id=org_id)
    db.add(policy)
    try:
        await db.flush()
    except IntegrityError:
        # Lost a race with another request creating the same singleton row.
        await db.rollback()
        result = await db.execute(select(GovernancePolicy).where(GovernancePolicy.org_id == org_id))
        policy = result.scalar_one()

    return policy


async def update_policy(
    db: AsyncSession,
    org_id: str,
    updated_by: str,
    risk_threshold_low: int | None = None,
    risk_threshold_high: int | None = None,
    environment_policies: dict | None = None,
) -> GovernancePolicy:
    policy = await get_or_create_policy(db, org_id)

    new_low = policy.risk_threshold_low if risk_threshold_low is None else risk_threshold_low
    new_high = policy.risk_threshold_high if risk_threshold_high is None else risk_threshold_high
    if new_low < 0 or new_high < 0:
        raise ValueError("Risk thresholds must be non-negative")
    if new_low > new_high:
        raise ValueError("risk_threshold_low cannot be greater than risk_threshold_high")

    if environment_policies is not None:
        merged = {**DEFAULT_ENVIRONMENT_POLICIES, **policy.environment_policies, **environment_policies}
        _validate_environment_policies(merged)
        policy.environment_policies = merged

    policy.risk_threshold_low = new_low
    policy.risk_threshold_high = new_high
    policy.updated_by = updated_by

    await db.flush()
    return policy


async def list_forbidden_rules(db: AsyncSession, org_id: str) -> list[ForbiddenEndpointRule]:
    result = await db.execute(
        select(ForbiddenEndpointRule)
        .where(ForbiddenEndpointRule.org_id == org_id)
        .order_by(ForbiddenEndpointRule.created_at.desc())
    )
    return list(result.scalars().all())


async def create_forbidden_rule(
    db: AsyncSession,
    org_id: str,
    path_pattern: str,
    created_by: str,
    method: str | None = None,
) -> ForbiddenEndpointRule:
    path_pattern = path_pattern.strip()
    if not path_pattern:
        raise ValueError("path_pattern is required")

    rule = ForbiddenEndpointRule(
        org_id=org_id,
        method=method.strip().upper() if method else None,
        path_pattern=path_pattern,
        created_by=created_by,
    )
    db.add(rule)
    await db.flush()
    return rule


async def delete_forbidden_rule(db: AsyncSession, org_id: str, rule_id: str) -> bool:
    result = await db.execute(
        select(ForbiddenEndpointRule).where(
            ForbiddenEndpointRule.id == rule_id, ForbiddenEndpointRule.org_id == org_id
        )
    )
    rule = result.scalar_one_or_none()
    if rule is None:
        return False

    await db.delete(rule)
    await db.flush()
    return True
