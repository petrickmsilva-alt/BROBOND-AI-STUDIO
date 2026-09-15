from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _token() -> dict:
    """PR002: persona creation and training are tenant actions and need a token."""

    response = client.post(
        "/api/v1/auth/register",
        json={"email": f"lora-{uuid4()}@example.com", "name": "LoRA Test", "password": "strong-pass-123"},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_lora_training_requires_reference_dataset() -> None:
    headers = _token()
    persona = client.post("/api/v1/personas", headers=headers, json={"name": "Test Persona", "age": 30, "appearance": "Athletic", "eye_color": "Brown", "height_m": 1.8, "style": "Realism"}).json()
    response = client.post(f"/api/v1/personas/{persona['id']}/train", headers=headers, json={"reference_asset_ids": [str(uuid4()) for _ in range(3)]})
    assert response.status_code == 422


def test_lora_training_queues_valid_dataset() -> None:
    headers = _token()
    persona = client.post("/api/v1/personas", headers=headers, json={"name": "Trained Persona", "age": 30, "appearance": "Athletic", "eye_color": "Brown", "height_m": 1.8, "style": "Realism"}).json()
    response = client.post(f"/api/v1/personas/{persona['id']}/train", headers=headers, json={"reference_asset_ids": [str(uuid4()) for _ in range(20)]})
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    status = client.get(f"/api/v1/personas/{persona['id']}/training/{body['run_id']}", headers=headers)
    assert status.status_code == 200
    assert status.json()["progress"] == 0
