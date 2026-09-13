def test_register_success(client):
    res = client.post("/api/v1/register", json={"email": "a@b.com", "password": "password123"})
    assert res.status_code == 201
    data = res.get_json()["data"]
    assert data["user"]["email"] == "a@b.com"
    assert data["access_token"]


def test_register_duplicate_email(client):
    client.post("/api/v1/register", json={"email": "a@b.com", "password": "password123"})
    res = client.post("/api/v1/register", json={"email": "a@b.com", "password": "password123"})
    assert res.status_code == 409


def test_register_short_password(client):
    res = client.post("/api/v1/register", json={"email": "a@b.com", "password": "short"})
    assert res.status_code == 400


def test_login_success(client):
    client.post("/api/v1/register", json={"email": "a@b.com", "password": "password123"})
    res = client.post("/api/v1/login", json={"email": "a@b.com", "password": "password123"})
    assert res.status_code == 200
    assert res.get_json()["data"]["access_token"]


def test_login_wrong_password(client):
    client.post("/api/v1/register", json={"email": "a@b.com", "password": "password123"})
    res = client.post("/api/v1/login", json={"email": "a@b.com", "password": "wrongpass"})
    assert res.status_code == 401


def test_me_requires_token(client):
    res = client.get("/api/v1/me")
    assert res.status_code == 401


def test_me_with_token(client, auth_user):
    _email, token = auth_user
    res = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.get_json()["data"]["user"]["email"] == "user@example.com"

def test_login_tracks_last_login_and_count(client):
    client.post("/api/v1/register", json={"email": "track@test.com", "password": "password123"})
    client.post("/api/v1/login", json={"email": "track@test.com", "password": "password123"})
    res = client.post("/api/v1/login", json={"email": "track@test.com", "password": "password123"})
    assert res.status_code == 200
    data = res.get_json()["data"]["user"]
    assert data["login_count"] == 2
    assert data["last_login_at"] is not None
