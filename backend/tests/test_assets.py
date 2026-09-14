from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _token() -> str:
    response = client.post("/api/v1/auth/register", json={"email": f"assets-{uuid4()}@example.com", "name": "Asset Owner", "password": "strong-pass-123"})
    return response.json()["access_token"]


def test_upload_and_list_asset() -> None:
    headers = {"Authorization": f"Bearer {_token()}"}
    upload = client.post("/api/v1/assets/upload", headers=headers, files={"file": ("portrait.jpg", b"fake-image-bytes", "image/jpeg")})
    assert upload.status_code == 201
    body = upload.json()
    assert body["kind"] == "image"
    assert body["name"] == "portrait.jpg"

    listed = client.get("/api/v1/assets", headers=headers)
    assert listed.status_code == 200
    assert listed.json()[0]["name"] == "portrait.jpg"
