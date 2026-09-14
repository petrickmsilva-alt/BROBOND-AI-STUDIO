from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_media_capabilities_endpoint() -> None:
    response = client.get("/api/v1/system/media")
    assert response.status_code == 200
    assert "available" in response.json()
    assert "mp4" in response.json()["formats"]
