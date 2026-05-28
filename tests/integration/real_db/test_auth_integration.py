def test_login_admin_success(client, seeded_users):
    response = client.post(
        "/auth/login",
        json={"email": seeded_users["admin_email"], "password": seeded_users["admin_password"]},
    )
    assert response.status_code == 200
    assert "access_token" in response.json()


def test_login_wrong_password_fails(client, seeded_users):
    response = client.post(
        "/auth/login",
        json={"email": seeded_users["admin_email"], "password": "wrong-password"},
    )
    assert response.status_code == 401


def test_me_requires_token(client):
    response = client.get("/auth/me")
    assert response.status_code == 401


def test_me_with_token(client, admin_token):
    response = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    assert response.json()["role"] == "admin"
