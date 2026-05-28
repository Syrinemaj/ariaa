def test_reports_runs_requires_auth(client):
    response = client.get("/reports/runs")
    assert response.status_code == 401


def test_reports_runs_pagination(client, admin_token):
    response = client.get(
        "/reports/runs?page=1&page_size=10",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert data["page"] == 1
    assert data["page_size"] == 10


def test_reports_page_size_too_large_rejected(client, admin_token):
    response = client.get(
        "/reports/runs?page=1&page_size=1000",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 422


def test_audit_logs_pagination(client, admin_token):
    response = client.get(
        "/audit-logs?page=1&page_size=20",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 1
    assert data["page_size"] == 20
    assert "total_pages" in data
