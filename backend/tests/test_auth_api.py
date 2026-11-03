from fastapi.testclient import TestClient


def test_live_public(client: TestClient):
    anon = TestClient(client.app)
    resp = anon.get("/api/v1/health/live")
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "alive"


def test_protected_requires_auth(client: TestClient):
    anon = TestClient(client.app)
    assert anon.get("/api/v1/system/status").status_code == 401
    assert anon.get("/api/v1/tasks").status_code == 401


def test_login_me_logout(client: TestClient, owner_credentials):
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["data"]["kind"] == "owner"
    assert client.post("/api/v1/auth/logout").status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401


def test_invalid_login(client: TestClient):
    anon = TestClient(client.app)
    resp = anon.post("/api/v1/auth/login", json={"username": "owner", "password": "wrong"})
    assert resp.status_code == 401


def test_invalid_token(client: TestClient):
    anon = TestClient(client.app)
    resp = anon.get("/api/v1/system/status", headers={"Authorization": "Bearer invalid"})
    assert resp.status_code == 401
