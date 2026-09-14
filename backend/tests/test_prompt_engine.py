from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_prompt_enhancement_returns_cinematic_prompt() -> None:
    response = client.post("/api/v1/prompts/enhance", json={"prompt": "A man walking", "persona": "a Brazilian athletic man"})
    assert response.status_code == 200
    body = response.json()
    assert body["original"] == "A man walking"
    assert "cinematic" in body["enhanced"]
    assert len(body["tokens"]) > 3
