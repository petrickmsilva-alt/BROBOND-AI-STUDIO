from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_gpu_capability_endpoint_is_safe_without_nvidia() -> None:
    response = client.get("/api/v1/system/gpu")
    assert response.status_code == 200
    assert "available" in response.json()


def test_image_parameters_are_persisted_on_job() -> None:
    response = client.post("/api/v1/generations/images", json={"prompt": "Test portrait", "steps": 36, "seed": 42})
    assert response.status_code == 202
    body = response.json()
    assert body["parameters"]["steps"] == 36
    assert body["parameters"]["seed"] == 42
