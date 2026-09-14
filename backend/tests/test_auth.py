from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_register_login_and_me() -> None:
    email = "petrick@example.com"
    registered = client.post("/api/v1/auth/register", json={"email": email, "name": "Petrick", "password": "strong-pass-123"})
    assert registered.status_code == 201
    token = registered.json()["access_token"]

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == email

    logged_in = client.post("/api/v1/auth/login", json={"email": email, "password": "strong-pass-123"})
    assert logged_in.status_code == 200
    assert logged_in.json()["token_type"] == "bearer"


def test_duplicate_email_is_rejected() -> None:
    payload = {"email": "duplicate@example.com", "name": "First User", "password": "strong-pass-123"}
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    assert client.post("/api/v1/auth/register", json=payload).status_code == 409
