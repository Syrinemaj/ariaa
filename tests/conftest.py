import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.models.user import UserRole


def make_har_bytes(entries=None):
    if entries is None:
        entries = [
            {
                "request": {
                    "method": "GET",
                    "url": "https://api.example.com/v1/users",
                    "headers": [{"name": "content-type", "value": "application/json"}],
                    "postData": None,
                },
                "response": {
                    "status": 200,
                    "headers": [{"name": "content-type", "value": "application/json"}],
                    "content": {"mimeType": "application/json", "text": '{"users": []}'},
                },
            }
        ]
    return json.dumps({"log": {"entries": entries}}).encode()


def _make_mock_admin():
    user = MagicMock()
    user.id = "mock-admin-id"
    user.org_id = "mock-org-id"
    user.email = "admin@aria.local"
    user.role = UserRole.ADMIN
    user.is_active = True
    return user


@pytest.fixture(scope="session")
def client():
    mock_admin = _make_mock_admin()

    with patch("app.main.init_db", return_value=None):
        from app.main import app
        from app.db.session import get_db
        from app.auth.dependencies import (
            get_current_user,
            require_admin,
            require_admin_or_operator,
        )

        def override_get_db():
            yield MagicMock()

        app.dependency_overrides[get_db] = lambda: (yield MagicMock())
        app.dependency_overrides[get_current_user] = lambda: mock_admin
        app.dependency_overrides[require_admin] = lambda: mock_admin
        app.dependency_overrides[require_admin_or_operator] = lambda: mock_admin

        with TestClient(app, raise_server_exceptions=True) as c:
            yield c

        app.dependency_overrides.clear()


@pytest.fixture
def har_bytes():
    return make_har_bytes()
