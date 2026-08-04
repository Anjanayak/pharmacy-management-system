from .conftest import register_user, login, auth_headers


def test_register_and_login_success(client):
    register_user(client, "alice", "alicepass123", role="staff")
    data = login(client, "alice", "alicepass123")
    assert data["access_token"]
    assert data["refresh_token"]
    assert data["role"] == "staff"
    assert data["username"] == "alice"


def test_login_wrong_password_returns_401(client):
    register_user(client, "bob", "bobpass123", role="staff")
    resp = client.post("/api/auth/login", data={"username": "bob", "password": "wrongpass"})
    assert resp.status_code == 401


def test_login_nonexistent_user_returns_401(client):
    resp = client.post("/api/auth/login", data={"username": "ghost", "password": "whatever"})
    assert resp.status_code == 401


def test_duplicate_username_rejected(client):
    register_user(client, "carol", "carolpass123")
    resp = client.post("/api/auth/register", json={
        "username": "carol", "email": "carol2@test-demo.com",
        "password": "anotherpass123", "full_name": "Carol Two", "role": "staff",
    })
    assert resp.status_code == 400


def test_protected_endpoint_requires_token(client):
    resp = client.get("/api/medicines")
    assert resp.status_code == 401


def test_invalid_token_rejected(client):
    resp = client.get("/api/medicines", headers=auth_headers("not-a-real-token"))
    assert resp.status_code == 401


def test_me_endpoint_returns_current_user(client):
    register_user(client, "dave", "davepass123", role="manager")
    token = login(client, "dave", "davepass123")["access_token"]
    resp = client.get("/api/auth/me", headers=auth_headers(token))
    assert resp.status_code == 200
    assert resp.json()["username"] == "dave"
    assert resp.json()["role"] == "manager"


def test_refresh_token_issues_new_working_access_token(client):
    register_user(client, "erin", "erinpass123", role="staff")
    tokens = login(client, "erin", "erinpass123")

    resp = client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert resp.status_code == 200
    new_tokens = resp.json()
    assert new_tokens["access_token"]
    assert new_tokens["refresh_token"]

    # the new access token should work on a protected endpoint
    me = client.get("/api/auth/me", headers=auth_headers(new_tokens["access_token"]))
    assert me.status_code == 200
    assert me.json()["username"] == "erin"


def test_refresh_rejects_garbage_token(client):
    resp = client.post("/api/auth/refresh", json={"refresh_token": "garbage.not.a.jwt"})
    assert resp.status_code == 401


def test_access_token_cannot_be_used_as_refresh_token(client):
    register_user(client, "frank", "frankpass123", role="staff")
    access_token = login(client, "frank", "frankpass123")["access_token"]
    resp = client.post("/api/auth/refresh", json={"refresh_token": access_token})
    assert resp.status_code == 401


# ---------- RBAC ----------

def test_staff_forbidden_from_creating_medicine(client, staff_headers):
    resp = client.post("/api/medicines", json={
        "name": "Test Med", "unit_price": 1.0,
    }, headers=staff_headers)
    assert resp.status_code == 403


def test_admin_can_create_medicine(client, admin_headers):
    resp = client.post("/api/medicines", json={
        "name": "Test Med", "unit_price": 1.0,
    }, headers=admin_headers)
    assert resp.status_code == 201


def test_manager_can_create_medicine(client, manager_headers):
    resp = client.post("/api/medicines", json={
        "name": "Test Med 2", "unit_price": 1.0,
    }, headers=manager_headers)
    assert resp.status_code == 201


def test_only_admin_can_list_users(client, admin_headers, manager_headers):
    resp = client.get("/api/auth/users", headers=admin_headers)
    assert resp.status_code == 200

    resp2 = client.get("/api/auth/users", headers=manager_headers)
    assert resp2.status_code == 403
