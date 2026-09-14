from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_local_workspace_e2e_flow() -> None:
    email = f"e2e-{uuid4()}@example.com"
    registered = client.post("/api/v1/auth/register", json={"email": email, "name": "E2E Owner", "password": "strong-pass-123"})
    assert registered.status_code == 201
    token = registered.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    upload = client.post("/api/v1/assets/upload", headers=headers, files={"file": ("reference.jpg", b"fake-image", "image/jpeg")})
    assert upload.status_code == 201
    assert upload.json()["kind"] == "image"

    generation = client.post("/api/v1/generations/images", headers=headers, json={"prompt": "A cinematic portrait", "seed": 7})
    assert generation.status_code == 202
    assert generation.json()["parameters"]["workspace_id"]

    storyboard = client.post("/api/v1/storyboards/expand", json={"brief": "A person crossing a neon city", "scene_count": 3, "persona": "consistent athletic character"})
    assert storyboard.status_code == 200
    assert len(storyboard.json()["scenes"]) == 3

    assets = client.get("/api/v1/assets", headers=headers)
    assert assets.status_code == 200
    assert any(asset["name"] == "reference.jpg" for asset in assets.json())
