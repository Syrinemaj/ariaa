def test_admin_can_list_users(client, admin_token):
    response = client.get(
        "/users",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    assert "users" in response.json()


def test_operator_cannot_list_users(client, operator_token):
    response = client.get(
        "/users",
        headers={"Authorization": f"Bearer {operator_token}"},
    )
    assert response.status_code == 403


def test_reports_requires_auth(client):
    response = client.get("/reports/summary")
    assert response.status_code == 401


def test_operator_can_view_reports(client, operator_token):
    response = client.get(
        "/reports/summary",
        headers={"Authorization": f"Bearer {operator_token}"},
    )
    assert response.status_code in {200, 404}


def test_audit_logs_requires_auth(client):
    response = client.get("/audit-logs")
    assert response.status_code == 401


def test_operator_can_view_audit_logs(client, operator_token):
    response = client.get(
        "/audit-logs",
        headers={"Authorization": f"Bearer {operator_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "logs" in data
    assert "total" in data
