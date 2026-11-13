from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.connection import Connection, ConnectionOperator
from app.models.organization import Organization
from app.models.user import User, UserRole


def _get_or_create_org(db):
    # See tests/integration/real_db/test_governance_models.py — same reason
    # (get_or_create_default_org is async-only, these tests use the sync
    # `db` fixture).
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
        email=f"conn-test-{uuid4()}@example.com",
        hashed_password="x",
        full_name="Connection Test User",
        role=role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_create_and_read_connection(db):
    org = _get_or_create_org(db)

    conn = Connection(
        org_id=org.id,
        name=f"test-connection-{uuid4()}",
        base_url="https://example.com",
        environment="test",
        auth_type="api_key",
        encrypted_secret="not-a-real-token",
    )
    db.add(conn)
    db.commit()
    db.refresh(conn)

    assert conn.status == "active"
    assert conn.secret_rotated_at is None

    fetched = db.query(Connection).filter(Connection.id == conn.id).one()
    assert fetched.base_url == "https://example.com"
    assert fetched.environment == "test"

    db.delete(fetched)
    db.commit()


def test_connection_name_unique_per_org(db):
    org = _get_or_create_org(db)
    name = f"dup-connection-{uuid4()}"

    first = Connection(
        org_id=org.id, name=name, base_url="https://a.example.com",
        environment="test", auth_type="api_key", encrypted_secret="x",
    )
    db.add(first)
    db.commit()

    second = Connection(
        org_id=org.id, name=name, base_url="https://b.example.com",
        environment="prod", auth_type="service_account", encrypted_secret="y",
    )
    db.add(second)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    db.delete(db.query(Connection).filter(Connection.id == first.id).one())
    db.commit()


def test_connection_operator_assignment_and_unique_constraint(db):
    org = _get_or_create_org(db)
    operator = _make_user(db, org.id)

    conn = Connection(
        org_id=org.id, name=f"assign-connection-{uuid4()}", base_url="https://example.com",
        environment="preprod", auth_type="oauth_client_credentials", encrypted_secret="z",
    )
    db.add(conn)
    db.commit()

    link = ConnectionOperator(connection_id=conn.id, user_id=operator.id)
    db.add(link)
    db.commit()

    fetched = (
        db.query(ConnectionOperator)
        .filter(ConnectionOperator.connection_id == conn.id, ConnectionOperator.user_id == operator.id)
        .one()
    )
    assert fetched is not None

    # Same (connection_id, user_id) pair again -> unique constraint violation
    dup = ConnectionOperator(connection_id=conn.id, user_id=operator.id)
    db.add(dup)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    # Explicit order + separate commits — connection_operators FKs to both
    # connections and users, so it must go first regardless of how the ORM
    # would otherwise order a single flush.
    db.query(ConnectionOperator).filter(ConnectionOperator.connection_id == conn.id).delete()
    db.commit()
    db.query(Connection).filter(Connection.id == conn.id).delete()
    db.commit()
    db.query(User).filter(User.id == operator.id).delete()
    db.commit()
