from uuid import uuid4

import pytest

from app.db.session import AsyncSessionLocal
from app.governance import service as governance_service
from app.models.governance import DEFAULT_ENVIRONMENT_POLICIES, GovernancePolicy
from app.models.organization import Organization
from app.models.user import User, UserRole

# Shared session-scoped event_loop fixture lives in conftest.py (needed
# across files, not just within this one — see its docstring).


def _get_or_create_org(db):
    org = db.query(Organization).first()
    if org is not None:
        return org
    org = Organization(id=str(uuid4()), name=f"test-org-{uuid4()}")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _make_user(db, org_id):
    user = User(
        id=str(uuid4()),
        org_id=org_id,
        email=f"gov-test-{uuid4()}@example.com",
        hashed_password="x",
        full_name="Governance Test Admin",
        role=UserRole.ADMIN.value,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def org_and_admin(db):
    org = _get_or_create_org(db)
    admin = _make_user(db, org.id)
    yield org, admin
    db.query(User).filter(User.id == admin.id).delete()
    db.commit()


@pytest.fixture(autouse=True)
def _clean_policy(db, org_and_admin):
    org, _ = org_and_admin
    db.query(GovernancePolicy).filter(GovernancePolicy.org_id == org.id).delete()
    db.commit()
    yield
    db.query(GovernancePolicy).filter(GovernancePolicy.org_id == org.id).delete()
    db.commit()


@pytest.mark.asyncio
async def test_get_or_create_policy_creates_default_then_is_idempotent(org_and_admin):
    org, _ = org_and_admin
    async with AsyncSessionLocal() as session:
        first = await governance_service.get_or_create_policy(session, org.id)
        await session.commit()
        assert first.risk_threshold_low == 1
        assert first.risk_threshold_high == 10
        assert first.environment_policies == DEFAULT_ENVIRONMENT_POLICIES

        second = await governance_service.get_or_create_policy(session, org.id)
        assert second.id == first.id


@pytest.mark.asyncio
async def test_update_policy_rejects_low_greater_than_high(org_and_admin):
    org, admin = org_and_admin
    async with AsyncSessionLocal() as session:
        await governance_service.get_or_create_policy(session, org.id)
        await session.commit()

        with pytest.raises(ValueError):
            await governance_service.update_policy(
                session, org.id, updated_by=admin.id, risk_threshold_low=20, risk_threshold_high=5
            )


@pytest.mark.asyncio
async def test_update_policy_merges_environment_policies_partially(org_and_admin):
    org, admin = org_and_admin
    async with AsyncSessionLocal() as session:
        await governance_service.get_or_create_policy(session, org.id)
        await session.commit()

        updated = await governance_service.update_policy(
            session, org.id, updated_by=admin.id, environment_policies={"prod": "forbidden"}
        )
        await session.commit()

        assert updated.environment_policies["prod"] == "forbidden"
        # test/preprod untouched by the partial update
        assert updated.environment_policies["test"] == "full_access"
        assert updated.environment_policies["preprod"] == "full_access"
        assert updated.updated_by == admin.id


@pytest.mark.asyncio
async def test_update_policy_rejects_unknown_environment(org_and_admin):
    org, admin = org_and_admin
    async with AsyncSessionLocal() as session:
        await governance_service.get_or_create_policy(session, org.id)
        await session.commit()

        with pytest.raises(ValueError):
            await governance_service.update_policy(
                session, org.id, updated_by=admin.id, environment_policies={"staging": "full_access"}
            )


@pytest.mark.asyncio
async def test_update_policy_rejects_invalid_mode(org_and_admin):
    org, admin = org_and_admin
    async with AsyncSessionLocal() as session:
        await governance_service.get_or_create_policy(session, org.id)
        await session.commit()

        with pytest.raises(ValueError):
            await governance_service.update_policy(
                session, org.id, updated_by=admin.id, environment_policies={"prod": "sort-of-allowed"}
            )


@pytest.mark.asyncio
async def test_forbidden_rule_create_list_delete_round_trip(org_and_admin):
    org, admin = org_and_admin
    async with AsyncSessionLocal() as session:
        rule = await governance_service.create_forbidden_rule(
            session, org.id, path_pattern="/employees/*", created_by=admin.id, method="delete"
        )
        await session.commit()
        assert rule.method == "DELETE"  # normalized to uppercase

        rules = await governance_service.list_forbidden_rules(session, org.id)
        assert any(r.id == rule.id for r in rules)

        deleted = await governance_service.delete_forbidden_rule(session, org.id, rule.id)
        await session.commit()
        assert deleted is True

        rules_after = await governance_service.list_forbidden_rules(session, org.id)
        assert not any(r.id == rule.id for r in rules_after)


@pytest.mark.asyncio
async def test_delete_forbidden_rule_wrong_org_returns_false(org_and_admin):
    org, admin = org_and_admin
    other_org_id = str(uuid4())
    async with AsyncSessionLocal() as session:
        rule = await governance_service.create_forbidden_rule(
            session, org.id, path_pattern="/admin/*", created_by=admin.id
        )
        await session.commit()

        deleted = await governance_service.delete_forbidden_rule(session, other_org_id, rule.id)
        assert deleted is False

        await governance_service.delete_forbidden_rule(session, org.id, rule.id)
        await session.commit()


@pytest.mark.asyncio
async def test_create_forbidden_rule_requires_path_pattern(org_and_admin):
    org, admin = org_and_admin
    async with AsyncSessionLocal() as session:
        with pytest.raises(ValueError):
            await governance_service.create_forbidden_rule(
                session, org.id, path_pattern="   ", created_by=admin.id
            )
