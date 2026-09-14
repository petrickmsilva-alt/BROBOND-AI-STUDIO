from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_readiness_reports_all_required_checks() -> None:
    response = client.get("/api/v1/system/readiness")
    assert response.status_code == 200
    body = response.json()
    assert "ready" in body
    assert {"cuda", "ffmpeg", "diffusers", "torch", "celery"}.issubset(body["checks"])
