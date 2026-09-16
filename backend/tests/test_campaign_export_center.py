"""V3.3 — Export Center: the whole campaign in one ZIP.

Pins the manifest contract, the per-asset prompt/metadata entries, the
delivered binaries (real bytes only), determinism, the checksum and the
collision/refusal paths. Nothing here invents a file: an asset that has
not been delivered contributes text entries only.
"""
from __future__ import annotations

import hashlib
import json
import zipfile

import pytest

from app.campaign.brief_interpreter import CampaignValidationError
from app.campaign.export_center import (
    DELIVERY_FILENAMES,
    MANIFEST_VERSION,
    ExportPackage,
    asset_folder,
    build_manifest,
    build_zip,
    read_manifest,
)


def _asset(**overrides) -> dict:
    asset = {
        "id": "asset-1",
        "campaign_id": "camp-1",
        "day": 1,
        "kind": "reel",
        "label": "Reel 9:16",
        "medium": "video",
        "aspect_ratio": "9:16",
        "width": 1080,
        "height": 1920,
        "duration_seconds": 15,
        "prompt": "a prompt",
        "cta": "Vista o extraordinário.",
        "status": "planned",
        "output_key": None,
        "thumbnail_key": None,
        "position": 0,
    }
    asset.update(overrides)
    return asset


# ---------------------------------------------------------------------------
# Folders and filenames
# ---------------------------------------------------------------------------


def test_asset_folders_are_day_prefixed_and_stable() -> None:
    assert asset_folder(_asset(day=1, kind="reel")) == "01-reel"
    assert asset_folder(_asset(day=3, kind="cover")) == "03-cover"
    assert asset_folder(_asset(day=12, kind="feed")) == "12-feed"


def test_delivery_filenames_match_the_media() -> None:
    assert DELIVERY_FILENAMES["video"] == "delivery.mp4"
    assert DELIVERY_FILENAMES["image"] == "delivery.png"


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


def test_the_manifest_carries_campaign_brief_timeline_and_assets() -> None:
    manifest = build_manifest(
        {"id": "camp-1", "name": "coleção Legacy"},
        {"product": "Legacy", "objective": "launch"},
        [_asset()],
        [{"day": 1, "focus": "Lançamento"}],
    )
    assert manifest["manifest_version"] == MANIFEST_VERSION
    assert manifest["campaign"]["name"] == "coleção Legacy"
    assert manifest["brief"]["product"] == "Legacy"
    assert manifest["timeline"] == [{"day": 1, "focus": "Lançamento"}]
    assert manifest["assets"][0]["kind"] == "reel"


# ---------------------------------------------------------------------------
# The ZIP
# ---------------------------------------------------------------------------


def _asset_view_payloads() -> list[dict]:
    return [
        _asset(day=1, kind="reel", output_key="ws/reel.mp4"),
        _asset(day=4, kind="feed", medium="image", id="asset-2", output_key="ws/feed.png"),
    ]


def test_the_zip_contains_manifest_prompts_metadata_and_binaries() -> None:
    manifest = build_manifest({"id": "camp-1"}, {"product": "Legacy"}, _asset_view_payloads(), [])
    binaries = {
        "01-reel/delivery.mp4": b"real mp4 bytes",
        "04-feed/delivery.png": b"real png bytes",
    }
    package = build_zip(manifest, _asset_view_payloads(), binaries)

    with zipfile.ZipFile(io_bytes(package.data)) as archive:
        names = archive.namelist()
        assert "manifest.json" in names
        assert "01-reel/prompt.txt" in names
        assert "01-reel/metadata.json" in names
        assert "01-reel/delivery.mp4" in names
        assert "04-feed/delivery.png" in names
        assert archive.read("01-reel/delivery.mp4") == b"real mp4 bytes"
        prompt = archive.read("01-reel/prompt.txt").decode("utf-8")
        assert prompt == "a prompt"
        metadata = json.loads(archive.read("04-feed/metadata.json").decode("utf-8"))
        assert metadata["kind"] == "feed"
    # An undelivered asset ships text entries only — no invented binary.
    assert "01-reel/thumbnail.png" not in names


def io_bytes(data: bytes):
    import io

    return io.BytesIO(data)


def test_the_package_is_deterministic_and_checksummed() -> None:
    manifest = build_manifest({"id": "camp-1"}, {}, _asset_view_payloads(), [])
    first = build_zip(manifest, _asset_view_payloads(), {"01-reel/delivery.mp4": b"abc"})
    second = build_zip(manifest, _asset_view_payloads(), {"01-reel/delivery.mp4": b"abc"})

    assert first.data == second.data
    assert first.sha256 == second.sha256 == hashlib.sha256(first.data).hexdigest()
    assert first.file_count == len(first.entries) == len(second.entries)
    assert ExportPackage(data=b"", entries=(), file_count=0, sha256="x").file_count == 0


def test_read_manifest_round_trips() -> None:
    manifest = build_manifest({"id": "camp-1", "name": "coleção Legacy"}, {}, [], [])
    package = build_zip(manifest, [], None)
    assert read_manifest(package.data)["campaign"]["name"] == "coleção Legacy"


def test_colliding_entries_are_refused() -> None:
    assets = [_asset(day=1, kind="reel")]
    manifest = build_manifest({}, {}, assets, [])
    # The asset's own prompt.txt collides with this binary path.
    with pytest.raises(CampaignValidationError):
        build_zip(manifest, assets, {"01-reel/prompt.txt": b"duplicate"})


def test_non_binary_payloads_are_refused() -> None:
    manifest = build_manifest({}, {}, [], [])
    with pytest.raises(CampaignValidationError):
        build_zip(manifest, [], {"01-reel/delivery.mp4": "not bytes"})  # type: ignore[dict-item]


def test_an_empty_campaign_still_exports_its_manifest() -> None:
    package = build_zip(build_manifest({}, {}, [], []), [], None)
    with zipfile.ZipFile(io_bytes(package.data)) as archive:
        assert archive.namelist() == ["manifest.json"]
