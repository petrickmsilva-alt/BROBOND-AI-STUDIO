"""ETAPA 16 tests — the asset routes that need a real user and a real file.

`main.py` sat at 79% and most of the gap is in routes guarded by
`Depends(current_user)`: local download, reference conditioning, H.264 export
and the persona LoRA listing. They were unreachable from the suite because no
test registered a user first. These do, following the pattern `test_assets.py`
already established.
"""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.storage import storage

client = TestClient(app)


@pytest.fixture()
def media_root(monkeypatch, tmp_path) -> Path:
    """Point the storage service at a scratch directory."""

    monkeypatch.setattr(storage, "local_root", tmp_path)
    return tmp_path


@pytest.fixture()
def headers() -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": f"routes-{uuid4()}@example.com", "name": "Route Owner", "password": "strong-pass-123"},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _upload(headers: dict, name: str = "portrait.png", payload: bytes = b"fake-image-bytes", content_type: str = "image/png") -> dict:
    """`kind` is derived from the content type, so the test controls it there."""

    response = client.post(headers=headers, url="/api/v1/assets/upload", files={"file": (name, payload, content_type)})
    assert response.status_code == 201, response.text
    return response.json()


def _upload_video(headers: dict) -> dict:
    return _upload(headers, name="clip.mp4", payload=b"fake-video", content_type="video/mp4")


# ---------------------------------------------------------------------------
# GET /api/v1/assets/download/{object_key}
# ---------------------------------------------------------------------------


def test_download_serves_a_stored_file(headers, media_root) -> None:
    asset = _upload(headers)
    response = client.get(f"/api/v1/assets/download/{asset['object_key']}", headers=headers)
    assert response.status_code == 200
    assert response.content == b"fake-image-bytes"


def test_download_refuses_object_storage_mode(headers, media_root, monkeypatch) -> None:
    """With MinIO on, the signed URL is the answer, not a local read.

    The asset is uploaded first: with `storage_enabled` already on, the upload
    itself would try to reach MinIO at localhost:9000.
    """

    from app.core.config import settings

    asset = _upload(headers)
    monkeypatch.setattr(settings, "storage_enabled", True)
    response = client.get(f"/api/v1/assets/download/{asset['object_key']}", headers=headers)
    assert response.status_code == 404
    assert response.json()["detail"] == "Use the signed MinIO URL"


@pytest.mark.parametrize("key", ["/etc/passwd", ".", "/"])
def test_download_refuses_a_key_that_escapes_the_root(headers, media_root, key: str) -> None:
    """Measured, and the measurement corrected an assumption of mine.

    `../etc/passwd` and `..` never reach this route: the HTTP client normalises
    them, and `GET /api/v1/assets/download/..` actually lands on the asset list
    route and returns 200 with `[]` — not a traversal. The forms that do reach
    the guard are the absolute ones and the bare dot. `storage.local_path`
    refuses all five independently, which test_storage.py pins.
    """

    response = client.get(f"/api/v1/assets/download/{key}", headers=headers)
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid asset path"


def test_the_storage_guard_refuses_the_relative_escapes_too() -> None:
    """The five forms, checked where they are real rather than through HTTP."""

    for key in ("..", ".", "../..", "../../etc/passwd", "a/../../etc/passwd"):
        with pytest.raises(ValueError, match="Invalid asset path"):
            storage.local_path(key)


def test_download_refuses_a_key_with_no_file(headers, media_root) -> None:
    (media_root / "ws").mkdir(parents=True, exist_ok=True)
    response = client.get("/api/v1/assets/download/ws/absent.png", headers=headers)
    assert response.status_code == 404
    assert response.json()["detail"] == "Asset not found"


# ---------------------------------------------------------------------------
# POST /api/v1/assets/{id}/conditioning
# ---------------------------------------------------------------------------


def test_conditioning_refuses_openpose_outside_the_gpu_worker(headers, media_root) -> None:
    """OpenPose needs controlnet-aux and a GPU; the route says so instead of failing."""

    asset = _upload(headers)
    response = client.post(f"/api/v1/assets/{asset['id']}/conditioning", headers=headers, json={"mode": "pose"})
    assert response.status_code == 501
    assert "GPU worker" in response.json()["detail"]


def test_conditioning_reports_an_unknown_asset(headers, media_root) -> None:
    response = client.post(f"/api/v1/assets/{uuid4()}/conditioning", headers=headers, json={"mode": "edges"})
    assert response.status_code == 404
    assert response.json()["detail"] == "Reference image not found"


def test_conditioning_cannot_be_run_on_another_tenants_asset(headers, media_root) -> None:
    asset = _upload(headers)
    other = client.post(
        "/api/v1/auth/register",
        json={"email": f"other-{uuid4()}@example.com", "name": "Other Owner", "password": "strong-pass-123"},
    ).json()
    response = client.post(
        f"/api/v1/assets/{asset['id']}/conditioning",
        headers={"Authorization": f"Bearer {other['access_token']}"},
        json={"mode": "edges"},
    )
    assert response.status_code == 404, "a foreign asset must look absent, not forbidden"


def test_conditioning_refuses_a_non_image_asset(headers, media_root) -> None:
    asset = _upload_video(headers)
    assert asset["kind"] == "video"
    response = client.post(f"/api/v1/assets/{asset['id']}/conditioning", headers=headers, json={"mode": "edges"})
    assert response.status_code == 404


def test_conditioning_says_when_pillow_is_missing(headers, media_root, monkeypatch) -> None:
    """503, not 500: the dependency is the problem, not the request."""

    import builtins

    asset = _upload(headers)
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "PIL":
            raise ImportError("No module named 'PIL'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    response = client.post(f"/api/v1/assets/{asset['id']}/conditioning", headers=headers, json={"mode": "edges"})
    assert response.status_code == 503
    assert "Pillow is required" in response.json()["detail"]


# ---------------------------------------------------------------------------
# POST /api/v1/assets/{id}/export
# ---------------------------------------------------------------------------


def test_export_refuses_without_ffmpeg(headers, media_root) -> None:
    """This sandbox has no FFmpeg, which is exactly the state the route reports."""

    from app.media import media

    assert media.available is False, "the assumption behind this test no longer holds"
    asset = _upload(headers, name="clip.mp4", payload=b"fake-video")
    response = client.post(f"/api/v1/assets/{asset['id']}/export", headers=headers, json={"quality": "1080p"})
    assert response.status_code == 503
    assert "FFmpeg is not installed" in response.json()["detail"]


@pytest.fixture()
def ffmpeg_present(monkeypatch) -> None:
    """`available` is `shutil.which("ffmpeg") is not None`, so that is what moves."""

    from app import media as media_module

    monkeypatch.setattr(media_module.shutil, "which", lambda name: "/usr/bin/ffmpeg")
    assert media_module.media.available is True


def test_export_reports_an_unknown_asset(headers, media_root, ffmpeg_present) -> None:
    response = client.post(f"/api/v1/assets/{uuid4()}/export", headers=headers, json={"quality": "1080p"})
    assert response.status_code == 404
    assert response.json()["detail"] == "Asset not found"


def test_export_rejects_a_non_video_asset(headers, media_root, ffmpeg_present) -> None:
    asset = _upload(headers)
    assert asset["kind"] == "image"
    response = client.post(f"/api/v1/assets/{asset['id']}/export", headers=headers, json={"quality": "1080p"})
    assert response.status_code == 422
    assert "Only video assets" in response.json()["detail"]


def test_export_rejects_another_tenants_video(headers, media_root, ffmpeg_present) -> None:
    asset = _upload_video(headers)
    other = client.post(
        "/api/v1/auth/register",
        json={"email": f"other-{uuid4()}@example.com", "name": "Other Owner", "password": "strong-pass-123"},
    ).json()
    response = client.post(
        f"/api/v1/assets/{asset['id']}/export",
        headers={"Authorization": f"Bearer {other['access_token']}"},
        json={"quality": "1080p"},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/v1/personas/{id}/loras
# ---------------------------------------------------------------------------


def test_a_persona_with_no_completed_runs_has_no_versions(headers) -> None:
    response = client.get(f"/api/v1/personas/{uuid4()}/loras", headers=headers)
    assert response.status_code == 200
    assert response.json() == []


def test_loras_require_authentication() -> None:
    assert client.get(f"/api/v1/personas/{uuid4()}/loras").status_code == 401


# ---------------------------------------------------------------------------
# GET /api/v1/personas/{id}/training/{run_id}
# ---------------------------------------------------------------------------


def test_training_status_reports_an_unknown_run(headers) -> None:
    persona_id, run_id = uuid4(), uuid4()
    response = client.get(f"/api/v1/personas/{persona_id}/training/{run_id}", headers=headers)
    assert response.status_code == 404
    assert response.json()["detail"] == "Training run not found"


# ---------------------------------------------------------------------------
# WS /api/v1/personas/{id}/training/events/{run_id}
# ---------------------------------------------------------------------------


def test_the_training_socket_reports_a_missing_run_and_closes() -> None:
    """It must say so and stop, not poll a row that will never appear."""

    with client.websocket_connect(f"/api/v1/personas/{uuid4()}/training/events/{uuid4()}") as socket:
        message = socket.receive_json()
    assert message["status"] == "failed"
    assert message["progress"] == 100
    assert message["log"] == "Training run not found"


def test_the_training_socket_is_open_without_authentication() -> None:
    """Recorded, not endorsed: this socket has no auth guard.

    The run id is a random UUID, so it is not enumerable, but the endpoint does
    not check identity the way the HTTP status route does. Pinning the current
    behaviour keeps the gap visible instead of silently changing it here.
    """

    with client.websocket_connect(f"/api/v1/personas/{uuid4()}/training/events/{uuid4()}") as socket:
        assert socket.receive_json()["status"] == "failed"
