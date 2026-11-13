from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.governance import DEFAULT_ENVIRONMENT_POLICIES, ForbiddenEndpointRule, GovernancePolicy
from app.models.organization import Organization


def _get_or_create_org(db):
    # app.auth.service.get_or_create_default_org is async-only (AsyncSession);
    # these tests use the sync `db` fixture (see conftest.py), so fetch/create
    # the org directly rather than mixing session types.
    org = db.query(Organization).first()
    if org is not None:
        return org
    org = Organization(id=str(uuid4()), name=f"test-org-{uuid4()}")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def test_create_and_read_governance_policy(db):
    org = _get_or_create_org(db)
    # Clean slate — a previous test run (or seed) may have left one behind.
    db.query(GovernancePolicy).filter(GovernancePolicy.org_id == org.id).delete()
    db.commit()

    policy = GovernancePolicy(org_id=org.id)
    db.add(policy)
    db.commit()
    db.refresh(policy)

    assert policy.risk_threshold_low == 1
    assert policy.risk_threshold_high == 10
    assert policy.environment_policies == DEFAULT_ENVIRONMENT_POLICIES

    db.delete(policy)
    db.commit()


def test_governance_policy_is_singleton_per_org(db):
    org = _get_or_create_org(db)
    db.query(GovernancePolicy).filter(GovernancePolicy.org_id == org.id).delete()
    db.commit()

    first = GovernancePolicy(org_id=org.id)
    db.add(first)
    db.commit()

    second = GovernancePolicy(org_id=org.id)
    db.add(second)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    db.delete(db.query(GovernancePolicy).filter(GovernancePolicy.org_id == org.id).one())
    db.commit()


def test_create_and_read_forbidden_endpoint_rule(db):
    org = _get_or_create_org(db)

    rule = ForbiddenEndpointRule(org_id=org.id, method="DELETE", path_pattern="/employees/*")
    db.add(rule)
    db.commit()
    db.refresh(rule)

    fetched = db.query(ForbiddenEndpointRule).filter(ForbiddenEndpointRule.id == rule.id).one()
    assert fetched.method == "DELETE"
    assert fetched.path_pattern == "/employees/*"
    assert fetched.org_id == org.id

    db.delete(fetched)
    db.commit()


def test_forbidden_endpoint_rule_method_is_optional(db):
    org = _get_or_create_org(db)

    rule = ForbiddenEndpointRule(org_id=org.id, method=None, path_pattern="/admin/*")
    db.add(rule)
    db.commit()
    db.refresh(rule)

    assert rule.method is None

    db.delete(rule)
    db.commit()
