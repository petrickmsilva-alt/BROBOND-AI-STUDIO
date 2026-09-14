from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_login_returns_bearer_token() -> None:
    response = client.post("/api/v1/auth/login", json={"email": "creator@example.com", "password": "local-password"})
    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
