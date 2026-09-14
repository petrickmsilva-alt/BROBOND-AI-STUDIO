from fastapi.testclient import TestClient

from app.main import app
from app.providers.video import _dimensions

client = TestClient(app)


def test_video_models_are_exposed() -> None:
    response = client.get("/api/v1/models/video")
    assert response.status_code == 200
    assert response.json()[0]["id"] == "wan-2.1-t2v"


def test_video_dimensions_preserve_format() -> None:
    assert _dimensions("16:9") == (832, 480)
    assert _dimensions("9:16") == (480, 832)
