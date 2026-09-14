from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_image_job_is_queued() -> None:
    response = client.post(
        "/api/v1/generations/images",
        json={"prompt": "A cinematic portrait", "aspect_ratio": "16:9"},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["type"] == "image"
    assert body["status"] == "queued"


def test_storyboard_expands_into_requested_scenes() -> None:
    response = client.post(
        "/api/v1/storyboards/expand",
        json={"brief": "A man walking through a future city", "scene_count": 4},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["scenes"]) == 4
    assert "cinematic" in body["scenes"][0]["prompt"]
    assert "wide establishing shot" in body["scenes"][0]["prompt"]
