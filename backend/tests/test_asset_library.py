"""PR013 — V4.0.1 Cinematic Asset Studio: the backend suite.

Covers ETAPA 2 (multipart ingest), ETAPA 3's data (thumbnail + metadata
persisted), ETAPA 4 (detail + before/after) and ETAPA 5 (filters and
instant-search grammar) against the real application:

* routes through `TestClient`, workspace-scoped, against the local storage
  adapter (files land under `settings.local_media_dir`, as every storage
  test in this repo already accepts);
* the service directly for ingest internals (sha256, probe, thumbnail
  bytes) and for the pure filter matcher;
* `thumbnails.py` and `parse_tags`/`resolve_content_type` as pure units.

Fixtures are real PNG/JPEG/WEBP bytes rendered by Pillow inside the test —
a fake extension over fake bytes would test the accept-list but not the
pipeline.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import UploadFile
from fastapi.datastructures import Headers
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import delete

from app.assets import (
    ACCEPTED_CONTENT_TYPES,
    LibraryFilters,
    asset_library,
    build_image_thumbnail,
    parse_tags,
    probe_image,
)
from app.assets.library_schemas import build_entry_response
from app.assets.library_service import (
    _matches,
    _stem,
    resolve_content_type,
)
from app.assets.thumbnails import THUMBNAIL_FORMAT, THUMBNAIL_MAX_SIDE_PX
from app.db import SessionLocal
from app.main import app
from app.models import Asset, User, Workspace
from app.assets.library_models import AssetMetadata
from app.storage import storage

client = TestClient(app)


# --------------------------------------------------------------------------- #
# Fixtures                                                                     #
# --------------------------------------------------------------------------- #


def _token() -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": f"library-{uuid4()}@example.com", "name": "Curator", "password": "strong-pass-123"},
    )
    assert response.status_code == 201, response.text
    return response.json()["access_token"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _png_bytes(width: int = 640, height: int = 360, color: tuple[int, int, int] = (120, 60, 200)) -> bytes:
    image = Image.new("RGB", (width, height), color)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _jpeg_bytes(width: int = 480, height: int = 270) -> bytes:
    image = Image.new("RGB", (width, height), (30, 120, 90))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def _webp_bytes(width: int = 320, height: int = 180) -> bytes:
    image = Image.new("RGB", (width, height), (200, 120, 40))
    buffer = io.BytesIO()
    image.save(buffer, format="WEBP")
    return buffer.getvalue()


def _upload(
    token: str,
    name: str = "frame.png",
    data: bytes | None = None,
    content_type: str = "image/png",
    **fields: str,
):
    files = {"file": (name, data if data is not None else _png_bytes(), content_type)}
    return client.post("/api/v1/assets/library/upload", headers=_headers(token), files=files, data=fields)


@pytest.fixture()
def clean_library():
    """Each test owns its rows; uuid filenames keep them apart."""
    yield
    db = SessionLocal()
    try:
        db.execute(delete(AssetMetadata))
        db.execute(delete(Asset))
        db.commit()
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# thumbnails.py — pure units                                                   #
# --------------------------------------------------------------------------- #


def test_probe_image_reads_real_png_dimensions() -> None:
    probe = probe_image(_png_bytes(640, 360))
    assert probe is not None
    assert (probe.width, probe.height) == (640, 360)
    assert probe.format == "PNG"


def test_probe_image_reads_jpeg_and_webp() -> None:
    assert probe_image(_jpeg_bytes(480, 270)).width == 480  # type: ignore[union-attr]
    assert probe_image(_webp_bytes(320, 180)).height == 180  # type: ignore[union-attr]


def test_probe_image_returns_none_for_garbage() -> None:
    assert probe_image(b"this is not an image") is None
    assert probe_image(b"") is None


def test_thumbnail_is_a_real_png_within_the_box() -> None:
    thumb = build_image_thumbnail(_png_bytes(1200, 600))
    assert thumb is not None
    decoded = Image.open(io.BytesIO(thumb))
    assert decoded.format == THUMBNAIL_FORMAT
    assert max(decoded.width, decoded.height) <= THUMBNAIL_MAX_SIDE_PX
    # Aspect preserved: 2:1 in, 2:1 out.
    assert decoded.width == 2 * decoded.height


def test_thumbnail_keeps_small_images_inside_the_box() -> None:
    thumb = build_image_thumbnail(_webp_bytes(100, 80))
    decoded = Image.open(io.BytesIO(thumb))  # type: ignore[arg-type]
    assert (decoded.width, decoded.height) == (100, 80)


def test_thumbnail_returns_none_for_non_images() -> None:
    assert build_image_thumbnail(b"definitely bytes, not an image") is None


def test_thumbnail_handles_grayscale_and_palette_modes() -> None:
    gray = Image.new("L", (200, 100), 128)
    buffer = io.BytesIO()
    gray.save(buffer, format="PNG")
    thumb = build_image_thumbnail(buffer.getvalue())
    assert thumb is not None and Image.open(io.BytesIO(thumb)).size == (200, 100)


def test_thumbnail_honours_a_custom_max_side() -> None:
    thumb = build_image_thumbnail(_png_bytes(800, 400), max_side=200)
    decoded = Image.open(io.BytesIO(thumb))  # type: ignore[arg-type]
    assert (decoded.width, decoded.height) == (200, 100)


# --------------------------------------------------------------------------- #
# Accept-list and tag parsing — pure units                                     #
# --------------------------------------------------------------------------- #


def test_accepted_content_types_are_exactly_the_etapa1_list() -> None:
    assert set(ACCEPTED_CONTENT_TYPES) == {"image/png", "image/jpeg", "image/webp", "video/mp4", "video/quicktime"}


@pytest.mark.parametrize(
    ("content_type", "filename", "expected"),
    [
        ("image/png", "a.png", "image/png"),
        ("video/quicktime", "clip.mov", "video/quicktime"),
        ("file", "clip.mov", "video/quicktime"),  # extension fallback
        ("file", "still.webp", "image/webp"),
        ("file", "archive.zip", None),
        (None, None, None),
        ("application/pdf", "doc.pdf", None),
    ],
)
def test_resolve_content_type(content_type, filename, expected) -> None:
    assert resolve_content_type(content_type, filename) == expected


def test_parse_tags_normalises_and_dedupes() -> None:
    assert parse_tags(" Editorial, dusk,,EDITORIAL , 16:9 ") == ["editorial", "dusk", "16:9"]
    assert parse_tags("") == []
    assert parse_tags(None) == []


def test_stem_handles_paths_and_missing_extensions() -> None:
    assert _stem("folder/file.png") == "file"
    assert _stem("plain") == "plain"
    assert _stem(None) == "upload"


# --------------------------------------------------------------------------- #
# ETAPA 2 — multipart upload                                                   #
# --------------------------------------------------------------------------- #


def test_upload_persists_asset_thumbnail_and_metadata(clean_library) -> None:
    token = _token()
    data = _png_bytes(800, 450)
    response = _upload(
        token,
        data=data,
        project="Neon Solitude",
        persona="BROBOND / 01",
        provider="flux-schnell",
        seed="482019",
        tags="editorial, dusk",
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["kind"] == "image"
    assert body["has_metadata"] is True
    assert body["source"] == "upload"
    assert body["resolution"] == "800×450"
    assert body["width"] == 800 and body["height"] == 450
    assert body["size_bytes"] == len(data)
    assert body["sha256"] == hashlib.sha256(data).hexdigest()
    assert body["content_type"] == "image/png"
    assert body["project"] == "Neon Solitude"
    assert body["persona"] == "BROBOND / 01"
    assert body["provider"] == "flux-schnell"
    assert body["seed"] == 482019
    assert body["tags"] == ["editorial", "dusk"]
    assert body["url"].startswith("/api/v1/assets/download/")
    # The thumbnail exists, is served, and is a real small PNG.
    assert body["thumbnail_url"]
    thumb = client.get(body["thumbnail_url"], headers=_headers(token))
    assert thumb.status_code == 200
    decoded = Image.open(io.BytesIO(thumb.content))
    assert decoded.format == "PNG"
    assert max(decoded.size) <= THUMBNAIL_MAX_SIDE_PX
    # And the main file itself round-trips byte for byte.
    main = client.get(body["url"], headers=_headers(token))
    assert main.status_code == 200 and main.content == data


def test_upload_persists_rows_in_the_database(clean_library) -> None:
    token = _token()
    created = _upload(token).json()
    db = SessionLocal()
    try:
        asset = db.get(Asset, created["id"])
        metadata = db.scalar(select_metadata(created["id"]))
        assert asset is not None and asset.kind == "image"
        assert metadata is not None
        assert metadata.asset_id == asset.id
        assert metadata.workspace_id == asset.workspace_id
        assert json.loads(metadata.tags_json) == []
        assert metadata.thumbnail_key is not None
        # The thumbnail is really stored under its key.
        assert storage.exists(metadata.thumbnail_key)
        assert storage.exists(asset.object_key)
    finally:
        db.close()


def select_metadata(asset_id: str):
    from sqlalchemy import select

    return select(AssetMetadata).where(AssetMetadata.asset_id == asset_id)


def test_upload_jpeg_and_webp(clean_library) -> None:
    token = _token()
    jpeg = _upload(token, name="still.jpg", data=_jpeg_bytes(500, 300), content_type="image/jpeg")
    assert jpeg.status_code == 201 and jpeg.json()["resolution"] == "500×300"
    webp = _upload(token, name="tile.webp", data=_webp_bytes(220, 330), content_type="image/webp")
    assert webp.status_code == 201 and webp.json()["resolution"] == "220×330"


def test_upload_video_mp4_and_mov_have_no_thumbnail(clean_library) -> None:
    """ffmpeg is absent by design (docs/LIMITATIONS.md) — video entries are
    honest about the missing poster instead of inventing one."""
    token = _token()
    mp4 = _upload(token, name="clip.mp4", data=b"\x00\x00\x00\x18ftypmp42fake-body", content_type="video/mp4")
    assert mp4.status_code == 201, mp4.text
    body = mp4.json()
    assert body["kind"] == "video"
    assert body["thumbnail_url"] is None
    assert body["resolution"] is None and body["width"] is None

    # Browsers occasionally send .mov without a useful MIME — the extension
    # decides, exactly as resolve_content_type documents.
    mov = client.post(
        "/api/v1/assets/library/upload",
        headers=_headers(token),
        files={"file": ("take.mov", b"\x00\x00\x00\x14ftypqt  fake", "application/octet-stream")},
    )
    assert mov.status_code == 201, mov.text
    assert mov.json()["kind"] == "video"
    assert mov.json()["content_type"] == "video/quicktime"


@pytest.mark.parametrize(
    ("name", "data", "content_type"),
    [
        ("notes.txt", b"plain text", "text/plain"),
        ("archive.zip", b"PK\x03\x04", "application/zip"),
        ("anim.gif", b"GIF89a", "image/gif"),
    ],
)
def test_upload_rejects_unsupported_types(clean_library, name, data, content_type) -> None:
    response = _upload(_token(), name=name, data=data, content_type=content_type)
    assert response.status_code == 415
    assert "PNG" in response.json()["detail"]


def test_upload_rejects_an_empty_file(clean_library) -> None:
    response = _upload(_token(), data=b"")
    assert response.status_code == 422


def test_upload_rejects_oversize_files(clean_library, monkeypatch) -> None:
    monkeypatch.setattr("app.assets.library_service.MAX_UPLOAD_BYTES", 16)
    response = _upload(_token(), data=_png_bytes(64, 64))
    assert response.status_code == 413


def test_upload_requires_authentication(clean_library) -> None:
    response = client.post("/api/v1/assets/library/upload", files={"file": ("a.png", _png_bytes(), "image/png")})
    assert response.status_code == 401


def test_upload_with_unknown_before_asset_is_rejected(clean_library) -> None:
    response = _upload(_token(), before_asset_id=str(uuid4()))
    assert response.status_code == 422


def test_upload_audits_the_action(clean_library) -> None:
    token = _token()
    created = _upload(token).json()
    db = SessionLocal()
    try:
        from sqlalchemy import select

        from app.models import AuditLog

        entry = db.scalar(
            select(AuditLog).where(AuditLog.action == "asset.uploaded", AuditLog.resource_id == created["id"])
        )
        assert entry is not None
        assert json.loads(entry.detail)["content_type"] == "image/png"
        assert json.loads(entry.detail)["thumbnail"] is True
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# ETAPA 3 + 5 — listing, filters, search                                       #
# --------------------------------------------------------------------------- #


def _seed_library(token: str) -> dict[str, dict]:
    seed = {
        "hero": _upload(token, name="hero.png", project="Neon Solitude", persona="BROBOND / 01", provider="flux", tags="hero, editorial").json(),
        "bts": _upload(token, name="bts.jpg", data=_jpeg_bytes(), project="Neon Solitude", persona="", provider="upload", tags="behind-the-scenes").json(),
        "clip": _upload(token, name="teaser.mp4", data=b"mp4-bytes", content_type="video/mp4", project="Horizon", tags="teaser 4k").json(),
    }
    db = SessionLocal()
    try:
        hero = db.get(Asset, seed["hero"]["id"])
        hero.quality_score = 92
        hero.quality_status = "masterpiece"
        bts = db.get(Asset, seed["bts"]["id"])
        bts.quality_score = 47
        bts.quality_status = "retry"
        db.commit()
    finally:
        db.close()
    return seed


def test_list_returns_every_asset_newest_first(clean_library) -> None:
    token = _token()
    _seed_library(token)
    legacy = client.post("/api/v1/assets/upload", headers=_headers(token), files={"file": ("legacy.png", _png_bytes(), "image/png")})
    assert legacy.status_code == 201

    listed = client.get("/api/v1/assets/library", headers=_headers(token))
    assert listed.status_code == 200
    names = [entry["name"] for entry in listed.json()]
    assert names == ["legacy.png", "teaser.mp4", "bts.jpg", "hero.png"]
    # The legacy upload has no metadata row: it stays visible, honestly bare.
    legacy_entry = listed.json()[0]
    assert legacy_entry["has_metadata"] is False
    assert legacy_entry["thumbnail_url"] is None
    assert legacy_entry["size_bytes"] is None


def test_list_filters_by_kind_and_provider(clean_library) -> None:
    token = _token()
    _seed_library(token)
    videos = client.get("/api/v1/assets/library?kind=video", headers=_headers(token)).json()
    assert [entry["name"] for entry in videos] == ["teaser.mp4"]
    flux = client.get("/api/v1/assets/library?provider=FLUX", headers=_headers(token)).json()
    assert [entry["name"] for entry in flux] == ["hero.png"]


def test_list_filters_by_project_and_persona_case_insensitively(clean_library) -> None:
    token = _token()
    _seed_library(token)
    project = client.get("/api/v1/assets/library?project=neon%20solitude", headers=_headers(token)).json()
    assert {entry["name"] for entry in project} == {"hero.png", "bts.jpg"}
    persona = client.get("/api/v1/assets/library?persona=brobond%20/%2001", headers=_headers(token)).json()
    assert [entry["name"] for entry in persona] == ["hero.png"]


def test_list_filters_by_minimum_quality_score(clean_library) -> None:
    token = _token()
    _seed_library(token)
    passing = client.get("/api/v1/assets/library?min_score=80", headers=_headers(token)).json()
    assert [entry["name"] for entry in passing] == ["hero.png"]
    # An unscored asset never passes a score filter — NULL is unknown, not zero.
    assert all(entry["quality_score"] is not None for entry in passing)


def test_list_filters_by_date_range(clean_library) -> None:
    token = _token()
    seed = _seed_library(token)
    db = SessionLocal()
    try:
        hero = db.get(Asset, seed["hero"]["id"])
        hero.created_at = datetime.utcnow() - timedelta(days=2)
        db.commit()
    finally:
        db.close()

    yesterday = (datetime.utcnow() - timedelta(days=1)).isoformat()
    recent = client.get(f"/api/v1/assets/library?date_from={yesterday}", headers=_headers(token)).json()
    assert {entry["name"] for entry in recent} == {"teaser.mp4", "bts.jpg"}
    three_days_ago = (datetime.utcnow() - timedelta(days=3)).isoformat()
    everything = client.get(f"/api/v1/assets/library?date_from={three_days_ago}", headers=_headers(token)).json()
    assert len(everything) == 3
    window = client.get(f"/api/v1/assets/library?date_to={yesterday}", headers=_headers(token)).json()
    assert [entry["name"] for entry in window] == ["hero.png"]


def test_search_matches_name_kind_and_tags(clean_library) -> None:
    token = _token()
    _seed_library(token)
    by_name = client.get("/api/v1/assets/library?q=hero", headers=_headers(token)).json()
    assert [entry["name"] for entry in by_name] == ["hero.png"]
    by_kind = client.get("/api/v1/assets/library?q=VIDEO", headers=_headers(token)).json()
    assert [entry["name"] for entry in by_kind] == ["teaser.mp4"]
    by_tag = client.get("/api/v1/assets/library?q=4k", headers=_headers(token)).json()
    assert [entry["name"] for entry in by_tag] == ["teaser.mp4"]
    no_hit = client.get("/api/v1/assets/library?q=does-not-exist", headers=_headers(token)).json()
    assert no_hit == []


def test_list_is_workspace_scoped(clean_library) -> None:
    owner = _token()
    _seed_library(owner)
    outsider = _token()
    listed = client.get("/api/v1/assets/library", headers=_headers(outsider))
    assert listed.status_code == 200 and listed.json() == []
    detail = client.get("/api/v1/assets/library/x", headers=_headers(outsider))
    assert detail.status_code == 404


def test_list_rejects_an_out_of_range_score(clean_library) -> None:
    response = client.get("/api/v1/assets/library?min_score=101", headers=_headers(_token()))
    assert response.status_code == 422


def test_library_routes_handle_a_user_without_a_workspace(clean_library) -> None:
    """A token whose workspace row disappeared must get calm answers, not
    exceptions: `[]` for the list, 404 for upload and detail."""
    from sqlalchemy import delete as sql_delete

    token = _token()
    me = client.get("/api/v1/auth/me", headers=_headers(token)).json()
    db = SessionLocal()
    try:
        db.execute(sql_delete(Workspace).where(Workspace.owner_id == me["id"]))
        db.commit()
    finally:
        db.close()

    listed = client.get("/api/v1/assets/library", headers=_headers(token))
    assert listed.status_code == 200 and listed.json() == []
    uploaded = _upload(token)
    assert uploaded.status_code == 404
    detail = client.get(f"/api/v1/assets/library/{uuid4()}", headers=_headers(token))
    assert detail.status_code == 404


# --------------------------------------------------------------------------- #
# ETAPA 4 — detail and before/after                                            #
# --------------------------------------------------------------------------- #


def test_detail_resolves_the_before_after_pair(clean_library) -> None:
    token = _token()
    before = _upload(token, name="raw.png").json()
    after = _upload(token, name="graded.png", before_asset_id=before["id"]).json()
    assert after["before_asset_id"] == before["id"]

    detail = client.get(f"/api/v1/assets/library/{after['id']}", headers=_headers(token))
    assert detail.status_code == 200
    body = detail.json()
    assert body["before_url"] and body["before_url"].startswith("/api/v1/assets/download/")
    assert body["before_thumbnail_url"]
    fetched = client.get(body["before_url"], headers=_headers(token))
    assert fetched.status_code == 200


def test_detail_without_pair_has_null_before_fields(clean_library) -> None:
    token = _token()
    created = _upload(token).json()
    detail = client.get(f"/api/v1/assets/library/{created['id']}", headers=_headers(token)).json()
    assert detail["before_asset_id"] is None
    assert detail["before_url"] is None
    assert detail.get("before_thumbnail_url") is None


def test_detail_of_a_deleted_pair_drops_the_before_urls(clean_library) -> None:
    """A before reference whose asset vanished must not leak a dead URL."""
    token = _token()
    before = _upload(token, name="gone.png").json()
    after = _upload(token, name="kept.png", before_asset_id=before["id"]).json()
    db = SessionLocal()
    try:
        row = db.get(Asset, before["id"])
        meta = db.scalar(select_metadata(before["id"]))
        if meta:
            db.delete(meta)
        db.delete(row)
        db.commit()
    finally:
        db.close()
    detail = client.get(f"/api/v1/assets/library/{after['id']}", headers=_headers(token)).json()
    assert detail["before_url"] is None
    assert detail["before_asset_id"] == before["id"]  # the reference stays; the URL does not leak


# --------------------------------------------------------------------------- #
# Service-level coverage (ingest internals, match predicate, legacy rows)      #
# --------------------------------------------------------------------------- #


def _workspace_of(token: str) -> str:
    db = SessionLocal()
    try:
        user_id = client.get("/api/v1/auth/me", headers=_headers(token)).json()["id"]
        user = db.get(User, user_id)
        workspace = db.query(Workspace).filter(Workspace.owner_id == user.id).first()
        return workspace.id
    finally:
        db.close()


def _upload_file(name: str = "svc.png", data: bytes | None = None, content_type: str = "image/png") -> UploadFile:
    return UploadFile(
        file=io.BytesIO(data if data is not None else _png_bytes()),
        filename=name,
        headers=Headers({"content-type": content_type}),
    )


def test_service_ingest_default_fields(clean_library) -> None:
    token = _token()
    workspace_id = _workspace_of(token)
    db = SessionLocal()
    try:
        record = asyncio.run(asset_library.ingest(db, workspace_id, file=_upload_file(name="plain.png")))
        assert record.has_metadata
        assert record.metadata.provider == "upload"
        assert record.metadata.project == ""
        assert record.resolution is not None
        assert build_entry_response(record, asset_library.url_for).provider == "upload"
    finally:
        db.close()


def test_service_ingest_non_image_bytes_as_video(clean_library) -> None:
    token = _token()
    workspace_id = _workspace_of(token)
    db = SessionLocal()
    try:
        record = asyncio.run(
            asset_library.ingest(db, workspace_id, file=_upload_file(name="clip.mp4", data=b"fake-mp4", content_type="video/mp4"))
        )
        assert record.metadata.thumbnail_key is None
        assert record.resolution is None
    finally:
        db.close()


def test_service_ingest_image_that_fails_probe_still_uploads(clean_library, monkeypatch) -> None:
    """A corrupt image body over a valid MIME uploads without dimensions or
    thumbnail — the row exists, the unknowns stay NULL."""
    monkeypatch.setattr("app.assets.library_service.probe_image", lambda data: None)
    monkeypatch.setattr("app.assets.library_service.build_image_thumbnail", lambda data: None)
    token = _token()
    workspace_id = _workspace_of(token)
    db = SessionLocal()
    try:
        record = asyncio.run(asset_library.ingest(db, workspace_id, file=_upload_file(name="broken.png", data=b"nope")))
        assert record.metadata.width is None
        assert record.metadata.thumbnail_key is None
    finally:
        db.close()


def test_matches_predicates_cover_every_branch(clean_library) -> None:
    from app.assets.library_service import LibraryRecord

    asset = Asset(name="Card.png", kind="image", workspace_id="w", object_key="k", quality_score=88)
    metadata = AssetMetadata(
        asset_id=asset.id,
        workspace_id="w",
        content_type="image/png",
        size_bytes=10,
        sha256="x",
        project="Proj",
        persona="Ana",
        provider="flux",
        tags_json=json.dumps(["dusk"]),
    )
    record = LibraryRecord(asset=asset, metadata=metadata, tags=("dusk",))
    base = LibraryFilters()
    assert _matches(record, base)
    assert _matches(record, LibraryFilters(kind="image")) and not _matches(record, LibraryFilters(kind="video"))
    assert _matches(record, LibraryFilters(min_score=80)) and not _matches(record, LibraryFilters(min_score=95))
    assert _matches(record, LibraryFilters(query="dusk"))
    assert not _matches(record, LibraryFilters(query="missing"))
    assert _matches(record, LibraryFilters(project="proj", persona="ana", provider="flux"))
    assert not _matches(record, LibraryFilters(project="other"))

    # A record without metadata only survives filters that do not need it.
    bare = LibraryRecord(
        asset=Asset(id=str(uuid4()), name="bare.mp4", kind="video", workspace_id="w", object_key="k", created_at=datetime(2026, 9, 1)),
        metadata=None,
        tags=(),
    )
    assert _matches(bare, LibraryFilters(kind="video"))
    assert not _matches(bare, LibraryFilters(project="proj"))
    assert not _matches(bare, LibraryFilters(min_score=1))
    assert not _matches(bare, LibraryFilters(persona="Ana"))
    assert not _matches(bare, LibraryFilters(provider="flux"))
    assert bare.resolution is None
    response = build_entry_response(bare, lambda key: f"/x/{key}" if key else None)
    assert response.has_metadata is False
    assert response.tags == []
    assert response.thumbnail_url is None
    assert response.url == "/x/k"


def test_matches_date_boundaries(clean_library) -> None:
    from app.assets.library_service import LibraryRecord

    when = datetime(2026, 9, 10, 12, 0, 0)
    asset = Asset(name="d.png", kind="image", workspace_id="w", object_key="k", created_at=when)
    record = LibraryRecord(asset=asset, metadata=None, tags=())
    assert _matches(record, LibraryFilters(date_from=when - timedelta(hours=1)))
    assert not _matches(record, LibraryFilters(date_from=when + timedelta(hours=1)))
    assert _matches(record, LibraryFilters(date_to=when + timedelta(hours=1)))
    assert not _matches(record, LibraryFilters(date_to=when - timedelta(hours=1)))


def test_url_for_none_key_is_none_safe() -> None:
    assert asset_library.url_for(None) is None
    assert asset_library.url_for("some/key.png") == "/api/v1/assets/download/some/key.png"


def test_blank_query_behaves_as_no_query(clean_library) -> None:
    token = _token()
    _seed_library(token)
    listed = client.get("/api/v1/assets/library?q=%20%20", headers=_headers(token)).json()
    assert len(listed) == 3


def test_corrupt_tags_document_reads_as_empty(clean_library) -> None:
    """A hand-edited or partially migrated `tags` column must not 500 the list."""
    from app.assets.library_service import _to_record

    asset = Asset(id=str(uuid4()), name="t.png", kind="image", workspace_id="w", object_key="k", created_at=datetime(2026, 9, 1))
    metadata = AssetMetadata(
        asset_id=asset.id, workspace_id="w", content_type="image/png", size_bytes=1, sha256="x", tags_json="{not json"
    )
    record = _to_record(asset, metadata)
    assert record.tags == ()
    response = build_entry_response(record, lambda key: key)
    assert response.tags == []


def test_service_ingest_without_filename_mints_a_default_name(clean_library) -> None:
    token = _token()
    workspace_id = _workspace_of(token)
    db = SessionLocal()
    try:
        anonymous = UploadFile(file=io.BytesIO(_png_bytes()), filename=None, headers=Headers({"content-type": "image/png"}))
        record = asyncio.run(asset_library.ingest(db, workspace_id, file=anonymous))
        assert record.asset.name == "upload.png"
        assert record.metadata.thumbnail_key is not None
        assert record.metadata.thumbnail_key.endswith("upload.thumb.png")
    finally:
        db.close()


def test_thumbnail_failure_inside_pillow_returns_none(monkeypatch) -> None:
    """If Pillow decodes but fails mid-resize, the upload must still succeed
    without a thumbnail rather than dying (thumbnails.py, defensive branch)."""
    image = Image.new("RGB", (64, 64), (1, 2, 3))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    data = buffer.getvalue()

    def _explode(self, *args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(Image.Image, "thumbnail", _explode)
    assert build_image_thumbnail(data) is None
