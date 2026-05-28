import pytest
from fastapi.testclient import TestClient

from app.auth.service import create_user, get_or_create_default_org, get_user_by_email
from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.main import app
from app.models.user import UserRole


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    init_db()


@pytest.fixture()
def client():
    # Clear any overrides set by other conftest fixtures (e.g. session-scoped mock client)
    # so that real DB integration tests use actual dependencies.
    saved_overrides = app.dependency_overrides.copy()
    app.dependency_overrides.clear()
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.update(saved_overrides)


@pytest.fixture()
def db():
    database = SessionLocal()
    try:
        yield database
    finally:
        database.close()


@pytest.fixture()
def seeded_users(db):
    org = get_or_create_default_org(db)

    if not get_user_by_email(db, "admin_test@example.com"):
        create_user(
            db=db,
            org_id=org.id,
            email="admin_test@example.com",
            password="Admin@123",
            full_name="Admin Test",
            role=UserRole.ADMIN,
        )

    if not get_user_by_email(db, "operator_test@example.com"):
        create_user(
            db=db,
            org_id=org.id,
            email="operator_test@example.com",
            password="Operator@123",
            full_name="Operator Test",
            role=UserRole.OPERATOR,
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
