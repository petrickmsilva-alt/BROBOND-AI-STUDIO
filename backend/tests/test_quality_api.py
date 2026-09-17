"""V3.4 ETAPA 7 — the five quality routes, end to end over HTTP.

Every test registers a fresh user (hence a fresh workspace), so workspaces
isolate tenants the way production does. The suite pins status codes
(200/201/400/401/404/422), the audit rows the two mutations write, the
denormalised badge on `GET /assets`, and the sprint's central prohibition:
a decision records intent, it executes nothing.
"""
from __future__ import annotations

import io
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from PIL import Image

from app.db import SessionLocal
from app.main import app
from app.models import AuditLog

client = TestClient(app)


def _register(tag: str = "quality") -> dict[str, str]:
    email = f"{tag}-{uuid.uuid4()}@example.com"
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "name": "Quality Tester", "password": "correct-horse-battery-staple"},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _png_bytes(size=(1280, 720), color=(120, 90, 160)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, "PNG")
    return buffer.getvalue()


def _upload(headers: dict[str, str], *, name: str = "render.png", size=(1280, 720)) -> str:
    response = client.post(
        "/api/v1/assets/upload",
        headers=headers,
        files={"file": (name, _png_bytes(size=size), "image/png")},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _assess(headers: dict[str, str], asset_id: str, payload: dict | None = None):
    body = {
        "aspect_ratio": "16:9",
        "prompt_original": "cinematic truck golden hour",
        "prompt_compiled": "cinematic truck at golden hour, ultra detailed",
        "signals": {"face": 92.0, "hands": 90.0, "eyes": 93.0},
    }
    if payload is not None:
        body = payload
    return client.post(f"/api/v1/quality/assets/{asset_id}/assess", headers=headers, json=body)


# --------------------------------------------------------------------- assess


def test_assessing_a_real_upload_returns_the_full_report() -> None:
    headers = _register()
    asset_id = _upload(headers)
    response = _assess(headers, asset_id)
    assert response.status_code == 201, response.text
    body = response.json()
    assert 0 <= body["overall_score"] <= 100
    assert body["status"] in ("retry", "manual_review", "approved", "masterpiece")
    assert body["asset_id"] == asset_id
    criteria = {item["criterion"]: item for item in body["criteria"]}
    # Detector signals came from the request; pixels were probed from the file.
    assert criteria["face"]["source"] == "detector"
    assert criteria["lighting"]["source"] == "measured"
    assert criteria["color"]["source"] == "measured"
    assert criteria["prompt_fidelity"]["source"] == "measured"
    # Geometry was probed from the real file — the request sent none.
    assert body["facts"]["width"] == 1280
    assert body["facts"]["short_side"] == 720


def test_assessing_writes_the_audit_row() -> None:
    headers = _register()
    asset_id = _upload(headers)
    report_id = _assess(headers, asset_id).json()["id"]
    with SessionLocal() as db:
        entry = db.scalar(
            select(AuditLog).where(
                AuditLog.action == "quality.assessed", AuditLog.resource_id == report_id
            )
        )
        assert entry is not None
        assert entry.resource_type == "quality_report"


def test_the_asset_list_carries_the_badge_after_assessment() -> None:
    headers = _register()
    asset_id = _upload(headers)
    listed = client.get("/api/v1/assets", headers=headers).json()
    assert listed[0]["quality_score"] is None  # never assessed ≠ zero
    assert listed[0]["quality_status"] is None

    body = _assess(headers, asset_id).json()
    listed = client.get("/api/v1/assets", headers=headers).json()
    assert listed[0]["quality_score"] == body["overall_score"]
    assert listed[0]["quality_status"] == body["status"]
    assert listed[0]["quality_version"] == body["engine_version"]


def test_custom_weights_rebalance_a_single_assessment() -> None:
    headers = _register()
    asset_id = _upload(headers)
    balanced = _assess(
        headers, asset_id, {"signals": {"face": 0.0, "hands": 100.0, "eyes": 100.0}}
    ).json()
    weighted = _assess(
        headers,
        asset_id,
        {
            "signals": {"face": 0.0, "hands": 100.0, "eyes": 100.0},
            "weights": {"face": 900.0},
        },
    ).json()
    assert weighted["overall_score"] < balanced["overall_score"]


def test_an_unknown_aspect_ratio_is_a_422() -> None:
    headers = _register()
    asset_id = _upload(headers)
    response = _assess(headers, asset_id, {"aspect_ratio": "21:10"})
    assert response.status_code == 422


def test_a_bad_signal_is_a_422() -> None:
    headers = _register()
    asset_id = _upload(headers)
    response = _assess(headers, asset_id, {"signals": {"vibe": 50.0}})
    assert response.status_code == 422
    response = _assess(headers, asset_id, {"signals": {"face": 250.0}})
    assert response.status_code == 422


def test_a_non_media_asset_is_refused() -> None:
    headers = _register()
    upload = client.post(
        "/api/v1/assets/upload",
        headers=headers,
        files={"file": ("voice.mp3", b"fake-audio", "audio/mpeg")},
    )
    assert upload.status_code == 201
    response = _assess(headers, upload.json()["id"])
    assert response.status_code == 422
    assert "image and video" in response.json()["detail"]


# --------------------------------------------------------------------- report


def test_the_report_route_returns_the_latest_persisted_report() -> None:
    headers = _register()
    asset_id = _upload(headers)
    created = _assess(headers, asset_id).json()
    read = client.get(f"/api/v1/quality/assets/{asset_id}/report", headers=headers)
    assert read.status_code == 200
    assert read.json()["id"] == created["id"]
    assert read.json()["overall_score"] == created["overall_score"]


def test_an_unassessed_asset_has_no_report_404() -> None:
    headers = _register()
    asset_id = _upload(headers)
    response = client.get(f"/api/v1/quality/assets/{asset_id}/report", headers=headers)
    assert response.status_code == 404


def test_history_is_newest_first_and_append_only() -> None:
    headers = _register()
    asset_id = _upload(headers)
    first = _assess(headers, asset_id, {"signals": {"face": 20.0, "hands": 20.0, "eyes": 20.0}}).json()
    second = _assess(headers, asset_id).json()
    history = client.get(f"/api/v1/quality/assets/{asset_id}/history", headers=headers).json()
    assert [item["id"] for item in history] == [second["id"], first["id"]]


# ------------------------------------------------------------------- decision


def test_a_decision_is_recorded_and_audited_but_executes_nothing() -> None:
    headers = _register()
    asset_id = _upload(headers)
    created = _assess(headers, asset_id).json()
    response = client.post(
        f"/api/v1/quality/assets/{asset_id}/decision",
        headers=headers,
        json={"decision": "regenerate"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["operator_decision"] == "regenerate"
    # Nothing executed: same report id, same score, no new history row, and
    # no new render job appeared in the queue.
    assert body["id"] == created["id"]
    assert body["overall_score"] == created["overall_score"]
    history = client.get(f"/api/v1/quality/assets/{asset_id}/history", headers=headers).json()
    assert len(history) == 1
    queue = client.get("/api/v1/queue", headers=headers).json()
    assert queue == []
    with SessionLocal() as db:
        entry = db.scalar(
            select(AuditLog).where(
                AuditLog.action == "quality.decision", AuditLog.resource_id == created["id"]
            )
        )
        assert entry is not None


def test_an_unknown_decision_is_a_422_from_the_schema() -> None:
    headers = _register()
    asset_id = _upload(headers)
    _assess(headers, asset_id)
    response = client.post(
        f"/api/v1/quality/assets/{asset_id}/decision",
        headers=headers,
        json={"decision": "ship-it"},
    )
    assert response.status_code == 422


def test_a_decision_without_a_report_is_a_404() -> None:
    headers = _register()
    asset_id = _upload(headers)
    response = client.post(
        f"/api/v1/quality/assets/{asset_id}/decision",
        headers=headers,
        json={"decision": "approve"},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------- authorization


def test_all_four_tenant_routes_require_identity() -> None:
    asset_id = "any"
    assert _assess({}, asset_id).status_code == 401
    assert client.get(f"/api/v1/quality/assets/{asset_id}/report").status_code == 401
    assert client.get(f"/api/v1/quality/assets/{asset_id}/history").status_code == 401
    assert (
        client.post(f"/api/v1/quality/assets/{asset_id}/decision", json={"decision": "approve"}).status_code
        == 401
    )


def test_a_foreign_tenant_reads_404_not_403() -> None:
    owner = _register("owner")
    other = _register("other")
    asset_id = _upload(owner)
    _assess(owner, asset_id)
    assert _assess(other, asset_id).status_code == 404
    assert client.get(f"/api/v1/quality/assets/{asset_id}/report", headers=other).status_code == 404
    assert client.get(f"/api/v1/quality/assets/{asset_id}/history", headers=other).status_code == 404
    assert (
        client.post(
            f"/api/v1/quality/assets/{asset_id}/decision", headers=other, json={"decision": "approve"}
        ).status_code
        == 404
    )


# --------------------------------------------------------------------- config


def test_the_config_route_is_public_reference_data() -> None:
    response = client.get("/api/v1/quality/config")
    assert response.status_code == 200
    body = response.json()
    assert body["retry_below"] == 70
    assert body["approved_at"] == 85
    assert body["masterpiece_at"] == 95
    assert len(body["criteria"]) == 8
    assert "motion" not in body["image_criteria"]
    assert "motion" in body["video_criteria"]
    assert set(body["weights"]) == set(body["criteria"])
    assert body["statuses"] == ["retry", "manual_review", "approved", "masterpiece"]
    assert body["sources"] == ["measured", "detector"]
