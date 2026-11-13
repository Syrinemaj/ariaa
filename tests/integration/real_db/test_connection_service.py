from uuid import uuid4

import pytest

from app.connections import service as connection_service
from app.db.session import AsyncSessionLocal
from app.models.automation import AutomationRun
from app.models.connection import Connection, ConnectionOperator
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


def _make_user(db, org_id, role=UserRole.OPERATOR.value):
    user = User(
        id=str(uuid4()),
        org_id=org_id,
        email=f"conn-svc-test-{uuid4()}@example.com",
        hashed_password="x",
        full_name="Connection Service Test User",
        role=role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def org_and_users(db):
    org = _get_or_create_org(db)
    admin = _make_user(db, org.id, UserRole.ADMIN.value)
    operator = _make_user(db, org.id, UserRole.OPERATOR.value)
    yield org, admin, operator

    # Delete ConnectionOperator rows by connection_id (not by user_id) — any
    # stale link from a leftover connection in this shared org would
    # otherwise survive and block the Connection delete below with a FK
    # violation, regardless of which user it points to.
    connection_ids = [row[0] for row in db.query(Connection.id).filter(Connection.org_id == org.id).all()]
    if connection_ids:
        db.query(ConnectionOperator).filter(ConnectionOperator.connection_id.in_(connection_ids)).delete(
            synchronize_session=False
        )
        # AutomationRun.connection_id (added in migration 022, Phase 4 Step 9)
        # also FKs to connections — real runs from manual/e2e verification
        # against this same shared org can reference these rows. Detach
        # rather than delete: connection_id is nullable and those runs are
        # real execution history, not test fixtures to discard.
        db.query(AutomationRun).filter(AutomationRun.connection_id.in_(connection_ids)).update(
            {"connection_id": None}, synchronize_session=False
        )
        db.commit()
    db.query(Connection).filter(Connection.org_id == org.id).delete()
    db.commit()
    db.query(User).filter(User.id.in_([admin.id, operator.id])).delete()
    db.commit()


@pytest.mark.asyncio
async def test_create_connection_encrypts_secret(org_and_users):
    org, admin, _ = org_and_users
    async with AsyncSessionLocal() as session:
        conn = await connection_service.create_connection(
            session, org.id, name=f"c-{uuid4()}", base_url="https://api.example.com",
            environment="test", auth_type="api_key", secret="super-secret-value", created_by=admin.id,
        )
        await session.commit()

        assert conn.encrypted_secret != "super-secret-value"
        assert connection_service.get_decrypted_secret_for_execution(conn) == "super-secret-value"


@pytest.mark.asyncio
async def test_create_connection_rejects_duplicate_name(org_and_users):
    org, admin, _ = org_and_users
    name = f"dup-{uuid4()}"
    async with AsyncSessionLocal() as session:
        await connection_service.create_connection(
            session, org.id, name=name, base_url="https://a.example.com",
            environment="test", auth_type="api_key", secret="x", created_by=admin.id,
        )
        await session.commit()

        with pytest.raises(ValueError, match="already exists"):
            await connection_service.create_connection(
                session, org.id, name=name, base_url="https://b.example.com",
                environment="prod", auth_type="service_account", secret="y", created_by=admin.id,
            )


@pytest.mark.asyncio
async def test_create_connection_validates_environment_and_auth_type(org_and_users):
    org, admin, _ = org_and_users
    async with AsyncSessionLocal() as session:
        with pytest.raises(ValueError, match="environment"):
            await connection_service.create_connection(
                session, org.id, name=f"c-{uuid4()}", base_url="https://x.example.com",
                environment="staging", auth_type="api_key", secret="x", created_by=admin.id,
            )

        with pytest.raises(ValueError, match="auth_type"):
            await connection_service.create_connection(
                session, org.id, name=f"c-{uuid4()}", base_url="https://x.example.com",
                environment="test", auth_type="basic_auth", secret="x", created_by=admin.id,
            )


@pytest.mark.asyncio
async def test_update_connection_partial_fields(org_and_users):
    org, admin, _ = org_and_users
    async with AsyncSessionLocal() as session:
        conn = await connection_service.create_connection(
            session, org.id, name=f"c-{uuid4()}", base_url="https://old.example.com",
            environment="test", auth_type="api_key", secret="x", created_by=admin.id,
        )
        await session.commit()
        original_secret = conn.encrypted_secret

        updated = await connection_service.update_connection(
            session, org.id, conn.id, base_url="https://new.example.com", environment="prod"
        )
        await session.commit()

        assert updated.base_url == "https://new.example.com"
        assert updated.environment == "prod"
        assert updated.encrypted_secret == original_secret  # update_connection never touches the secret


@pytest.mark.asyncio
async def test_rotate_secret_changes_value_and_sets_timestamp(org_and_users):
    org, admin, _ = org_and_users
    async with AsyncSessionLocal() as session:
        conn = await connection_service.create_connection(
            session, org.id, name=f"c-{uuid4()}", base_url="https://x.example.com",
            environment="test", auth_type="api_key", secret="old-secret", created_by=admin.id,
        )
        await session.commit()
        assert conn.secret_rotated_at is None

        rotated = await connection_service.rotate_secret(session, org.id, conn.id, "new-secret")
        await session.commit()

        assert rotated.secret_rotated_at is not None
        assert connection_service.get_decrypted_secret_for_execution(rotated) == "new-secret"


@pytest.mark.asyncio
async def test_revoke_and_reactivate_connection(org_and_users):
    org, admin, _ = org_and_users
    async with AsyncSessionLocal() as session:
        conn = await connection_service.create_connection(
            session, org.id, name=f"c-{uuid4()}", base_url="https://x.example.com",
            environment="test", auth_type="api_key", secret="x", created_by=admin.id,
        )
        await session.commit()

        revoked = await connection_service.revoke_connection(session, org.id, conn.id)
        await session.commit()
        assert revoked.status == "revoked"

        reactivated = await connection_service.reactivate_connection(session, org.id, conn.id)
        await session.commit()
        assert reactivated.status == "active"


@pytest.mark.asyncio
async def test_admin_sees_all_active_connections_operator_sees_only_assigned(org_and_users):
    org, admin, operator = org_and_users
    async with AsyncSessionLocal() as session:
        assigned = await connection_service.create_connection(
            session, org.id, name=f"assigned-{uuid4()}", base_url="https://x.example.com",
            environment="test", auth_type="api_key", secret="x", created_by=admin.id,
        )
        unassigned = await connection_service.create_connection(
            session, org.id, name=f"unassigned-{uuid4()}", base_url="https://y.example.com",
            environment="test", auth_type="api_key", secret="y", created_by=admin.id,
        )
        await session.commit()

        await connection_service.assign_operator(session, org.id, assigned.id, operator.id)
        await session.commit()

        admin_view = await connection_service.list_usable_connections(session, org.id, admin)
        admin_ids = {c.id for c in admin_view}
        assert assigned.id in admin_ids and unassigned.id in admin_ids

        operator_view = await connection_service.list_usable_connections(session, org.id, operator)
        operator_ids = {c.id for c in operator_view}
        assert operator_ids == {assigned.id}


@pytest.mark.asyncio
async def test_revoked_connection_excluded_from_usable_list(org_and_users):
    org, admin, _ = org_and_users
    async with AsyncSessionLocal() as session:
        conn = await connection_service.create_connection(
            session, org.id, name=f"c-{uuid4()}", base_url="https://x.example.com",
            environment="test", auth_type="api_key", secret="x", created_by=admin.id,
        )
        await session.commit()
        await connection_service.revoke_connection(session, org.id, conn.id)
        await session.commit()

        admin_view = await connection_service.list_usable_connections(session, org.id, admin)
        assert conn.id not in {c.id for c in admin_view}


@pytest.mark.asyncio
async def test_assign_operator_duplicate_rejected(org_and_users):
    org, admin, operator = org_and_users
    async with AsyncSessionLocal() as session:
        conn = await connection_service.create_connection(
            session, org.id, name=f"c-{uuid4()}", base_url="https://x.example.com",
            environment="test", auth_type="api_key", secret="x", created_by=admin.id,
        )
        await session.commit()

        await connection_service.assign_operator(session, org.id, conn.id, operator.id)
        await session.commit()

        with pytest.raises(ValueError, match="already assigned"):
            await connection_service.assign_operator(session, org.id, conn.id, operator.id)


@pytest.mark.asyncio
async def test_unassign_operator_round_trip(org_and_users):
    org, admin, operator = org_and_users
    async with AsyncSessionLocal() as session:
        conn = await connection_service.create_connection(
            session, org.id, name=f"c-{uuid4()}", base_url="https://x.example.com",
            environment="test", auth_type="api_key", secret="x", created_by=admin.id,
        )
        await session.commit()

        await connection_service.assign_operator(session, org.id, conn.id, operator.id)
        await session.commit()
        assert operator.id in await connection_service.list_operator_ids(session, conn.id)

        unassigned = await connection_service.unassign_operator(session, org.id, conn.id, operator.id)
        await session.commit()
        assert unassigned is True
        assert operator.id not in await connection_service.list_operator_ids(session, conn.id)


@pytest.mark.asyncio
async def test_assign_operator_nonexistent_user_rejected(org_and_users):
    org, admin, _ = org_and_users
    async with AsyncSessionLocal() as session:
        conn = await connection_service.create_connection(
            session, org.id, name=f"c-{uuid4()}", base_url="https://x.example.com",
            environment="test", auth_type="api_key", secret="x", created_by=admin.id,
        )
        await session.commit()

        with pytest.raises(ValueError, match="User not found"):
            await connection_service.assign_operator(session, org.id, conn.id, "does-not-exist")
