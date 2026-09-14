from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_lora_training_requires_reference_dataset() -> None:
    persona = client.post("/api/v1/personas", json={"name": "Test Persona", "age": 30, "appearance": "Athletic", "eye_color": "Brown", "height_m": 1.8, "style": "Realism"}).json()
    response = client.post(f"/api/v1/personas/{persona['id']}/train", json={"reference_asset_ids": [str(uuid4()) for _ in range(3)]})
    assert response.status_code == 422


def test_lora_training_queues_valid_dataset() -> None:
    persona = client.post("/api/v1/personas", json={"name": "Trained Persona", "age": 30, "appearance": "Athletic", "eye_color": "Brown", "height_m": 1.8, "style": "Realism"}).json()
    response = client.post(f"/api/v1/personas/{persona['id']}/train", json={"reference_asset_ids": [str(uuid4()) for _ in range(20)]})
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    status = client.get(f"/api/v1/personas/{persona['id']}/training/{body['run_id']}")
    assert status.status_code == 200
    assert status.json()["progress"] == 0
