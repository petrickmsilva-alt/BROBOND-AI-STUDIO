from uuid import uuid4

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


def test_authenticated_generation_targets_workspace() -> None:
    registration = client.post("/api/v1/auth/register", json={"email": f"critical-output-{uuid4()}@example.com", "name": "Output Owner", "password": "strong-pass-123"})
    token = registration.json()["access_token"]
    response = client.post("/api/v1/generations/images", headers={"Authorization": f"Bearer {token}"}, json={"prompt": "Persist this output"})
    assert response.status_code == 202
    assert response.json()["parameters"]["workspace_id"]
