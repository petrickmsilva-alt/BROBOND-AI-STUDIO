"""V3.3 — the seven campaign routes, end to end over HTTP.

Every test registers a fresh user (hence a fresh workspace), so workspaces
isolate tenants the way production does. The suite pins status codes
(200/201/401/404/422), the audit rows each mutation writes, the Export
Center ZIP actually stored (read back through the same storage adapter the
route used), and the planned → delivered transition with a real file.
"""
from __future__ import annotations

import io
import json
import uuid
import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.models import AuditLog
from app.storage import storage

client = TestClient(app)

#: A real 1×1 PNG — delivered campaign files must be real files.
PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d494844520000000100000001080600000"
    "01f15c4890000000d49444154789c626001000000ffff030000060005"
    "57bfabd40000000049454e44ae426082"
)


def _register(tag: str = "campaign") -> tuple[str, dict[str, str]]:
    email = f"{tag}-{uuid.uuid4()}@example.com"
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "name": "Campaign Test", "password": "correct-horse-battery-staple"},
    )
    assert response.status_code == 201, response.text
    token = response.json()["access_token"]
    return email, {"Authorization": f"Bearer {token}"}


def _workspace_id(headers: dict[str, str]) -> str:
    response = client.get("/api/v1/auth/me", headers=headers)
    me = response.json()
    with SessionLocal() as db:
        from app.models import Workspace

        row = db.scalar(select(Workspace).where(Workspace.owner_id == me["id"]))
        assert row is not None
        return row.id


def _latest(action: str) -> AuditLog | None:
    with SessionLocal() as db:
        return db.scalar(
            select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.created_at.desc())
        )


def _put_file(workspace_id: str, name: str, payload: bytes) -> str:
    """Store one real file where the local storage adapter looks for it."""

    path = storage.local_path(f"{workspace_id}/{name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return f"{workspace_id}/{name}"


def _create(headers: dict[str, str], briefing: str = "Quero lançar a coleção Legacy para o público premium no instagram, vídeos de 15s", name: str | None = None) -> dict:
    payload: dict = {"briefing": briefing}
    if name:
        payload["name"] = name
    response = client.post("/api/v1/campaigns", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------


def test_every_campaign_route_requires_a_token() -> None:
    assert client.post("/api/v1/campaigns/interpret", json={"briefing": "x"}).status_code == 401
    assert client.post("/api/v1/campaigns", json={"briefing": "x"}).status_code == 401
    assert client.get("/api/v1/campaigns").status_code == 401
    assert client.get("/api/v1/campaigns/any").status_code == 401
    assert client.post("/api/v1/campaigns/any/duplicate", json={}).status_code == 401
    assert client.post("/api/v1/campaigns/any/assets/any/deliver", json={}).status_code == 401
    assert client.post("/api/v1/campaigns/any/export").status_code == 401


# ---------------------------------------------------------------------------
# Interpret
# ---------------------------------------------------------------------------


def test_interpret_returns_the_six_fields_without_persisting() -> None:
    _, headers = _register()
    response = client.post(
        "/api/v1/campaigns/interpret",
        json={"briefing": "Quero lançar a coleção Legacy para o público jovem no tiktok"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {
        "raw_text", "name", "product", "product_type", "audience", "platform",
        "objective", "duration_seconds", "missing", "matched",
    }
    assert body["product"] == "Legacy"
    assert body["product_type"] == "coleção"
    assert body["platform"] == "tiktok"
    assert body["audience"] == "público jovem"
    assert body["name"] == "coleção Legacy"
    assert "plataforma" not in body["missing"]
    assert "duração" in body["missing"]
    assert client.get("/api/v1/campaigns", headers=headers).json() == []


def test_interpret_validates_the_briefing() -> None:
    _, headers = _register()
    assert client.post("/api/v1/campaigns/interpret", json={"briefing": "   "}, headers=headers).status_code == 422
    assert client.post("/api/v1/campaigns/interpret", json={"briefing": ""}, headers=headers).status_code == 422
    assert client.post("/api/v1/campaigns/interpret", json={}, headers=headers).status_code == 422


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def test_one_briefing_creates_the_complete_campaign() -> None:
    _, headers = _register()
    body = _create(headers)

    assert body["name"] == "coleção Legacy"
    assert body["product"] == "Legacy"
    assert body["objective"] == "launch"
    assert body["status"] == "active"
    assert body["primary_cta"]

    assert len(body["assets"]) == 7
    kinds = sorted(asset["kind"] for asset in body["assets"])
    assert kinds == ["banner", "cover", "feed", "reel", "shorts", "story", "thumbnail"]
    reel = next(asset for asset in body["assets"] if asset["kind"] == "reel")
    assert reel["medium"] == "video" and reel["aspect_ratio"] == "9:16"
    assert (reel["width"], reel["height"], reel["duration_seconds"]) == (1080, 1920, 15)
    assert all(asset["status"] == "planned" for asset in body["assets"])
    assert all(asset["prompt"] for asset in body["assets"])

    assert [episode["day"] for episode in body["episodes"]] == [1, 2, 3, 4, 5]
    assert all(episode["cta"] for episode in body["episodes"])

    # The sprint rule: a campaign never repeats a CTA.
    ctas = [body["primary_cta"]] + [asset["cta"] for asset in body["assets"]]
    ctas += [episode["cta"] for episode in body["episodes"]]
    assert len({cta.casefold() for cta in ctas}) == len(ctas) == 13

    assert body["brief"]["raw_text"].startswith("Quero lançar")
    assert body["exports"] == []

    entry = _latest("campaign.created")
    assert entry is not None and entry.resource_type == "campaign"
    detail = json.loads(entry.detail or "{}")
    assert detail["assets"] == 7 and detail["product"] == "Legacy"


def test_create_rejects_a_blank_briefing() -> None:
    _, headers = _register()
    assert client.post("/api/v1/campaigns", json={"briefing": "  "}, headers=headers).status_code == 422


# ---------------------------------------------------------------------------
# List + detail
# ---------------------------------------------------------------------------


def test_list_and_detail_and_the_foreign_404() -> None:
    _, headers = _register()
    created = _create(headers, name="Legacy SS26")

    listed = client.get("/api/v1/campaigns", headers=headers).json()
    assert [campaign["id"] for campaign in listed] == [created["id"]]
    assert listed[0]["name"] == "Legacy SS26"

    detail = client.get(f"/api/v1/campaigns/{created['id']}", headers=headers)
    assert detail.status_code == 200
    body = detail.json()
    assert set(body) == {
        "id", "workspace_id", "name", "product", "product_type", "audience",
        "platform", "objective", "status", "seed", "primary_cta", "created_at",
        "updated_at", "brief", "assets", "episodes", "exports",
    }
    assert body["brief"]["product"] == "Legacy"
    assert len(body["assets"]) == 7 and len(body["episodes"]) == 5

    _, other = _register(tag="campaign-other")
    assert client.get(f"/api/v1/campaigns/{created['id']}", headers=other).status_code == 404
    assert client.get("/api/v1/campaigns/never", headers=headers).status_code == 404


# ---------------------------------------------------------------------------
# Duplicate
# ---------------------------------------------------------------------------


def test_duplicate_resets_deliveries_and_rearms_ctas() -> None:
    _, headers = _register()
    original = _create(headers)
    asset_id = original["assets"][0]["id"]
    workspace_id = _workspace_id(headers)
    key = _put_file(workspace_id, "render.png", PNG_1PX)
    delivered = client.post(
        f"/api/v1/campaigns/{original['id']}/assets/{asset_id}/deliver",
        json={"output_key": key},
        headers=headers,
    )
    assert delivered.status_code == 200, delivered.text
    assert delivered.json()["status"] == "delivered"

    response = client.post(
        f"/api/v1/campaigns/{original['id']}/duplicate", json={}, headers=headers
    )
    assert response.status_code == 201, response.text
    copy = response.json()
    assert copy["id"] != original["id"]
    assert copy["name"] == f"{original['name']} (cópia)"
    assert copy["seed"] != original["seed"]
    assert all(asset["status"] == "planned" for asset in copy["assets"])
    assert all(asset["output_key"] is None for asset in copy["assets"])

    original_ctas = [asset["cta"] for asset in original["assets"]]
    copy_ctas = [asset["cta"] for asset in copy["assets"]]
    assert copy_ctas != original_ctas
    assert len({cta.casefold() for cta in copy_ctas}) == len(copy_ctas)

    entry = _latest("campaign.duplicated")
    assert entry is not None
    assert json.loads(entry.detail or "{}")["source_campaign_id"] == original["id"]

    assert client.post("/api/v1/campaigns/never/duplicate", json={}, headers=headers).status_code == 404


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------


def test_delivery_validates_workspace_ownership_and_existence() -> None:
    _, headers = _register()
    created = _create(headers)
    asset_id = created["assets"][0]["id"]
    workspace_id = _workspace_id(headers)

    missing = client.post(
        f"/api/v1/campaigns/{created['id']}/assets/{asset_id}/deliver",
        json={"output_key": f"{workspace_id}/never-rendered.png"},
        headers=headers,
    )
    assert missing.status_code == 422

    foreign = client.post(
        f"/api/v1/campaigns/{created['id']}/assets/{asset_id}/deliver",
        json={"output_key": "someone-else/file.png"},
        headers=headers,
    )
    assert foreign.status_code == 422

    empty = client.post(
        f"/api/v1/campaigns/{created['id']}/assets/{asset_id}/deliver",
        json={},
        headers=headers,
    )
    assert empty.status_code == 422

    unknown_asset = client.post(
        f"/api/v1/campaigns/{created['id']}/assets/never/deliver",
        json={"output_key": f"{workspace_id}/x.png"},
        headers=headers,
    )
    assert unknown_asset.status_code == 404

    unknown_campaign = client.post(
        f"/api/v1/campaigns/never/assets/{asset_id}/deliver",
        json={"output_key": f"{workspace_id}/x.png"},
        headers=headers,
    )
    assert unknown_campaign.status_code == 404


def test_delivery_with_a_real_file_audits_and_persists() -> None:
    _, headers = _register()
    created = _create(headers)
    asset_id = created["assets"][0]["id"]
    workspace_id = _workspace_id(headers)
    key = _put_file(workspace_id, "renders/feed.png", PNG_1PX)

    response = client.post(
        f"/api/v1/campaigns/{created['id']}/assets/{asset_id}/deliver",
        json={"output_key": key, "thumbnail_key": key},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "delivered"
    assert body["output_key"] == key

    entry = _latest("campaign.asset.delivered")
    assert entry is not None and entry.resource_type == "campaign_asset"
    assert json.loads(entry.detail or "{}")["output_key"] == key

    reread = client.get(f"/api/v1/campaigns/{created['id']}", headers=headers).json()
    delivered = next(asset for asset in reread["assets"] if asset["id"] == asset_id)
    assert delivered["status"] == "delivered"


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def test_export_builds_a_real_zip_and_records_the_row() -> None:
    _, headers = _register()
    created = _create(headers)
    workspace_id = _workspace_id(headers)

    reel = next(asset for asset in created["assets"] if asset["kind"] == "reel")
    feed = next(asset for asset in created["assets"] if asset["kind"] == "feed")
    reel_key = _put_file(workspace_id, "renders/reel.mp4", b"real rendered mp4 bytes")
    feed_key = _put_file(workspace_id, "renders/feed.png", PNG_1PX)
    assert client.post(
        f"/api/v1/campaigns/{created['id']}/assets/{reel['id']}/deliver",
        json={"output_key": reel_key},
        headers=headers,
    ).status_code == 200
    assert client.post(
        f"/api/v1/campaigns/{created['id']}/assets/{feed['id']}/deliver",
        json={"output_key": feed_key},
        headers=headers,
    ).status_code == 200

    response = client.post(f"/api/v1/campaigns/{created['id']}/export", headers=headers)
    assert response.status_code == 201, response.text
    export = response.json()
    assert set(export) == {
        "id", "workspace_id", "campaign_id", "object_key", "download_url",
        "file_count", "sha256", "created_at",
    }
    assert export["object_key"].startswith(f"{workspace_id}/campaigns/{created['id']}/exports/")
    assert export["download_url"] == f"/api/v1/assets/download/{export['object_key']}"

    # The ZIP is really there, and it really contains the campaign.
    stored = storage.local_path(export["object_key"])
    assert stored.is_file()
    with zipfile.ZipFile(io.BytesIO(stored.read_bytes())) as archive:
        names = archive.namelist()
        assert "manifest.json" in names
        assert len([name for name in names if name.endswith("prompt.txt")]) == 7
        assert len([name for name in names if name.endswith("metadata.json")]) == 7
        assert "01-reel/delivery.mp4" in names
        assert "04-feed/delivery.png" in names
        assert archive.read("01-reel/delivery.mp4") == b"real rendered mp4 bytes"
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
    assert manifest["campaign"]["id"] == created["id"]
    assert len(manifest["timeline"]) == 5

    detail = client.get(f"/api/v1/campaigns/{created['id']}", headers=headers).json()
    assert [row["id"] for row in detail["exports"]] == [export["id"]]

    entry = _latest("campaign.exported")
    assert entry is not None and entry.resource_type == "campaign_export"
    assert json.loads(entry.detail or "{}")["file_count"] == export["file_count"]

    assert client.post("/api/v1/campaigns/never/export", headers=headers).status_code == 404


# ---------------------------------------------------------------------------
# Tenant isolation of the ZIP path
# ---------------------------------------------------------------------------


def test_a_foreign_token_cannot_touch_another_tenant_campaign() -> None:
    _, headers = _register()
    created = _create(headers)
    _, other = _register(tag="campaign-tenant")

    assert client.post(
        f"/api/v1/campaigns/{created['id']}/export", headers=other
    ).status_code == 404
    assert client.post(
        f"/api/v1/campaigns/{created['id']}/duplicate", json={}, headers=other
    ).status_code == 404
    other_list = client.get("/api/v1/campaigns", headers=other).json()
    assert other_list == []
