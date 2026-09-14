from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_conditioning_catalog() -> None:
    response = client.get("/api/v1/models/conditioning")
    assert response.status_code == 200
    ids = {item["id"] for item in response.json()}
    assert {"pose", "depth", "canny", "tile", "ip-adapter"}.issubset(ids)
