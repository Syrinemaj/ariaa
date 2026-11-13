import asyncio
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func

from app.auth.password import hash_password
from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.main import app
from app.models.organization import Organization
from app.models.user import User, UserRole


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    init_db()


@pytest.fixture(scope="session")
def event_loop():
    # Single event loop for every async test in this directory (not just
    # per-module). asyncpg's connection pool (async_engine, module-global in
    # app/db/session.py) has pool_pre_ping=True — a pooled connection
    # created under one event loop can't be pinged/closed from a different
    # one, which previously surfaced as "Event loop is closed" at the
    # boundary between two test files that each defined their own
    # module-scoped event_loop fixture. One loop for the whole session
    # avoids that regardless of file ordering.
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture()
def client():
    # Clear any overrides set by other conftest fixtures (e.g. session-scoped mock client)
    # so that real DB integration tests use actual dependencies.
    saved_overrides = app.dependency_overrides.copy()
    app.dependency_overrides.clear()
    # The /auth/login rate limit (5/minute, Redis-backed) is shared by every
    # test in the session: without a reset, later tests get HTTP 429 just
    # because earlier ones logged in. Each test starts with fresh counters.
    from app.core.rate_limit import limiter
    from app.db.session import async_engine
    limiter.reset()
    # Async tests in this directory (session-wide event_loop fixture) may have
    # left pooled connections bound to their loop; start from an empty pool.
    async_engine.sync_engine.dispose(close=False)
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.update(saved_overrides)
        # Each TestClient runs the app on its own event loop, which is closed
        # on exit. Pooled asyncpg connections stay bound to that dead loop and
        # break the next test ("Event loop is closed"). Drop them without
        # trying to close them on the dead loop.
        async_engine.sync_engine.dispose(close=False)


@pytest.fixture()
def db():
    database = SessionLocal()
    try:
        yield database
    finally:
        database.close()


def _get_or_create_default_org_sync(db) -> Organization:
    # app.auth.service.get_or_create_default_org is async-only (AsyncSession);
    # this fixture uses the sync `db` fixture above, so look up/create the
    # org directly rather than mixing session types (same reason as the
    # local _get_or_create_org() helpers in test_governance_models.py /
    # test_connection_models.py).
    from app.core.config import settings

    org = db.query(Organization).filter(Organization.name == settings.DEFAULT_ORG_NAME).first()
    if org is not None:
        return org
    # organizations.id has no column default (the app assigns a uuid4 in
    # app.auth.service.get_or_create_default_org) — without an explicit id
    # this INSERT fails with NotNullViolation on a fresh, empty database.
    org = Organization(id=str(uuid4()), name=settings.DEFAULT_ORG_NAME)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _get_or_create_user_sync(db, org_id: str, email: str, password: str, full_name: str, role) -> User:
    user = db.query(User).filter(func.lower(User.email) == email.lower()).first()
    if user is not None:
        return user
    user = User(
        org_id=org_id,
        email=email.lower(),
        full_name=full_name,
        hashed_password=hash_password(password),
        role=role.value if hasattr(role, "value") else role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def seeded_users(db):
    org = _get_or_create_default_org_sync(db)

    _get_or_create_user_sync(
        db, org.id, "admin_test@example.com", "Admin@123", "Admin Test", UserRole.ADMIN
    )
    _get_or_create_user_sync(
        db, org.id, "operator_test@example.com", "Operator@123", "Operator Test", UserRole.OPERATOR
    )

    return {
        "admin_email": "admin_test@example.com",
        "admin_password": "Admin@123",
        "operator_email": "operator_test@example.com",
        "operator_password": "Operator@123",
    }


def login_and_get_token(client: TestClient, email: str, password: str) -> str:
    response = client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.fixture()
def admin_token(client, seeded_users):
    return login_and_get_token(client, seeded_users["admin_email"], seeded_users["admin_password"])


@pytest.fixture()
def operator_token(client, seeded_users):
    return login_and_get_token(client, seeded_users["operator_email"], seeded_users["operator_password"])
