from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_prompt_enhancement_contract() -> None:
    response = client.post("/api/v1/prompts/enhance", json={"prompt": "man walking"})
    assert response.status_code == 200
    assert "cinematic composition" in response.json()["enhanced"]
