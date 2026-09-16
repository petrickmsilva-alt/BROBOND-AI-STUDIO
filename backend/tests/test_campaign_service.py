"""V3.3 — CampaignService: the whole builder flow, composed.

The service is the only module that imports the others. These tests use an
in-memory fake storage adapter, a fixed seed factory and a pass-through
prompt enhancer, so the orchestration is pinned without touching disk or
the GPU stack: briefing → deliverables → timeline → persistence,
duplication with freshly armed CTAs, delivery validation against real
stored files, and the export flow that packages what actually exists.
"""
from __future__ import annotations

import io
import json
import tempfile
import zipfile
from pathlib import Path
from uuid import uuid4

import pytest

# The campaign tables come from the Alembic bootstrap that runs at app
# import (the same shared-database reliance the continuity suite has).
from app.main import app  # noqa: F401
from app.campaign.brief_interpreter import CampaignValidationError
from app.campaign.campaign_repository import CampaignRepository
from app.campaign.campaign_service import (
    CampaignService,
    InvalidDeliveryError,
    UnknownAssetError,
    UnknownCampaignError,
)
from app.campaign.export_center import DELIVERY_FILENAMES, asset_folder, read_manifest


class FakeStorage:
    """The storage adapter's surface: real bytes, handed back as real files."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.uploads: list[tuple[str, str]] = []

    def put(self, key: str, payload: bytes) -> str:
        self.objects[key] = payload
        return key

    def exists(self, key: str) -> bool:
        return key in self.objects

    def download(self, key: str, destination=None) -> Path:
        if key not in self.objects:
            raise KeyError(key)
        with tempfile.NamedTemporaryFile(suffix="-fake-storage", delete=False) as handle:
            handle.write(self.objects[key])
            return Path(handle.name)

    def local_path(self, key: str) -> Path:
        return Path(f"/fake/{key}")

    def read(self, key: str) -> bytes:
        return self.objects[key]

    def upload_path(self, source, key: str, content_type: str = "") -> str:
        self.uploads.append((key, content_type))
        self.objects[key] = Path(source).read_bytes()
        return f"/signed/{key}"


@pytest.fixture()
def storage() -> FakeStorage:
    return FakeStorage()


@pytest.fixture()
def service(storage) -> CampaignService:
    seeds = iter(range(100, 1000))

    return CampaignService(
        repository=CampaignRepository(),
        storage_adapter=storage,
        prompt_enhancer=lambda prompt, style="": f"[{style}] {prompt}",
        seed_factory=lambda: next(seeds),
    )


# ---------------------------------------------------------------------------
# Creating
# ---------------------------------------------------------------------------


def test_one_briefing_builds_the_complete_campaign(service) -> None:
    ws = f"ws-{uuid4().hex}"
    bundle = service.create_from_briefing(ws, "Quero lançar a coleção Legacy")

    assert bundle.campaign.name == "coleção Legacy"
    assert isinstance(bundle.campaign.seed, int) and bundle.campaign.seed > 0
    assert bundle.campaign.primary_cta
    assert bundle.brief.cta == bundle.campaign.primary_cta
    assert len(bundle.assets) == 7
    assert len(bundle.episodes) == 5
    # The composed prompts went through the injected enhancer.
    assert all(asset.prompt.startswith("[cinematic realism]") for asset in bundle.assets)


def test_an_explicit_name_wins_over_the_interpreted_one(service) -> None:
    ws = f"ws-{uuid4().hex}"
    bundle = service.create_from_briefing(ws, "coleção Legacy", name="Lançamento Legacy")
    assert bundle.campaign.name == "Lançamento Legacy"


def test_a_blank_briefing_is_refused_before_anything_is_written(service) -> None:
    ws = f"ws-{uuid4().hex}"
    with pytest.raises(CampaignValidationError):
        service.create_from_briefing(ws, "   ")
    assert service.list_campaigns(ws) == []


def test_get_detail_returns_the_full_aggregate(service) -> None:
    ws = f"ws-{uuid4().hex}"
    bundle = service.create_from_briefing(ws, "coleção Legacy")
    detail = service.get_detail(ws, bundle.campaign.id)

    assert detail.campaign.id == bundle.campaign.id
    assert detail.brief is not None and detail.brief.product == "Legacy"
    assert len(detail.assets) == 7 and len(detail.episodes) == 5
    assert detail.exports == ()


def test_unknown_campaigns_and_assets_are_honest(service) -> None:
    ws = f"ws-{uuid4().hex}"
    with pytest.raises(UnknownCampaignError):
        service.get_detail(ws, "missing")

    bundle = service.create_from_briefing(ws, "coleção Legacy")
    with pytest.raises(UnknownCampaignError):
        service.deliver(ws, "missing", bundle.assets[0].id, output_key=f"{ws}/x.png")
    with pytest.raises(UnknownAssetError):
        service.deliver(ws, bundle.campaign.id, "missing", output_key=f"{ws}/x.png")


# ---------------------------------------------------------------------------
# Duplication
# ---------------------------------------------------------------------------


def test_duplicate_starts_clean_with_freshly_armed_ctas(service) -> None:
    ws = f"ws-{uuid4().hex}"
    original = service.create_from_briefing(ws, "Quero lançar a coleção Legacy")
    copy = service.duplicate(ws, original.campaign.id)

    assert copy.campaign.id != original.campaign.id
    assert copy.campaign.name == "coleção Legacy (cópia)"
    assert copy.campaign.seed != original.campaign.seed
    # Deliveries do not carry over and every asset is planned again.
    assert all(asset.status == "planned" for asset in copy.assets)
    assert all(asset.output_key is None for asset in copy.assets)
    # The CTA deck was re-armed: the copy's assignments differ from the origin.
    original_ctas = [asset.cta for asset in original.assets]
    copy_ctas = [asset.cta for asset in copy.assets]
    assert copy_ctas != original_ctas
    assert len({cta.casefold() for cta in copy_ctas}) == len(copy_ctas)
    # Same brief fields — the copy is the same campaign, re-run.
    assert copy.brief.product == original.brief.product
    assert copy.brief.audience == original.brief.audience


def test_duplicate_accepts_an_explicit_name(service) -> None:
    ws = f"ws-{uuid4().hex}"
    original = service.create_from_briefing(ws, "coleção Legacy")
    copy = service.duplicate(ws, original.campaign.id, name="Legacy Black Friday")
    assert copy.campaign.name == "Legacy Black Friday"


def test_duplicate_of_a_missing_campaign_is_a_404(service) -> None:
    with pytest.raises(UnknownCampaignError):
        service.duplicate(f"ws-{uuid4().hex}", "missing")


def test_each_build_draws_a_fresh_seed(service) -> None:
    ws = f"ws-{uuid4().hex}"
    first = service.create_from_briefing(ws, "coleção Legacy")
    second = service.create_from_briefing(ws, "coleção Legacy")
    assert first.campaign.seed != second.campaign.seed
    assert first.campaign.primary_cta != second.campaign.primary_cta


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------


def test_delivery_requires_a_real_file_of_the_workspace(service, storage) -> None:
    ws = f"ws-{uuid4().hex}"
    bundle = service.create_from_briefing(ws, "coleção Legacy")
    asset = bundle.assets[0]

    with pytest.raises(InvalidDeliveryError):
        service.deliver(ws, bundle.campaign.id, asset.id)
    with pytest.raises(InvalidDeliveryError):
        service.deliver(ws, bundle.campaign.id, asset.id, output_key="other-workspace/file.png")
    with pytest.raises(InvalidDeliveryError):
        service.deliver(ws, bundle.campaign.id, asset.id, output_key=f"{ws}/never-uploaded.png")

    key = storage.put(f"{ws}/renders/reel.mp4", b"mp4")
    delivered = service.deliver(
        ws, bundle.campaign.id, asset.id, output_key=key, thumbnail_key=None
    )
    assert delivered.status == "delivered"
    assert delivered.output_key == key


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def test_export_packages_manifest_prompts_and_delivered_files(service, storage) -> None:
    ws = f"ws-{uuid4().hex}"
    bundle = service.create_from_briefing(ws, "Quero lançar a coleção Legacy")

    reel = next(asset for asset in bundle.assets if asset.kind == "reel")
    feed = next(asset for asset in bundle.assets if asset.kind == "feed")
    reel_key = storage.put(f"{ws}/renders/reel.mp4", b"REAL MP4 BYTES")
    feed_key = storage.put(f"{ws}/renders/feed.png", b"REAL PNG BYTES")
    thumb_key = storage.put(f"{ws}/renders/reel-thumb.png", b"REAL THUMB BYTES")
    service.deliver(ws, bundle.campaign.id, reel.id, output_key=reel_key, thumbnail_key=thumb_key)
    service.deliver(ws, bundle.campaign.id, feed.id, output_key=feed_key)

    export = service.export(ws, bundle.campaign.id)

    assert export.object_key == f"{ws}/campaigns/{bundle.campaign.id}/exports/{export.id}.zip"
    assert storage.uploads and storage.uploads[0][0] == export.object_key
    assert storage.uploads[0][1] == "application/zip"
    assert export.file_count >= 1 + 7 * 2 + 3

    archive = zipfile.ZipFile(io.BytesIO(storage.objects[export.object_key]))
    names = archive.namelist()
    assert "manifest.json" in names
    assert f"{asset_folder(reel.to_dict())}/delivery.mp4" in names
    assert f"{asset_folder(feed.to_dict())}/delivery.png" in names
    assert f"{asset_folder(reel.to_dict())}/thumbnail.png" in names
    assert archive.read(f"{asset_folder(reel.to_dict())}/delivery.mp4") == b"REAL MP4 BYTES"

    manifest = read_manifest(storage.objects[export.object_key])
    assert manifest["campaign"]["id"] == bundle.campaign.id
    assert len(manifest["assets"]) == 7
    assert len(manifest["timeline"]) == 5
    assert any(asset["status"] == "delivered" for asset in manifest["assets"])

    detail = service.get_detail(ws, bundle.campaign.id)
    assert export.id in [view.id for view in detail.exports]


def test_export_of_a_fresh_campaign_ships_text_only(service, storage) -> None:
    ws = f"ws-{uuid4().hex}"
    bundle = service.create_from_briefing(ws, "coleção Legacy")
    export = service.export(ws, bundle.campaign.id)

    archive = zipfile.ZipFile(io.BytesIO(storage.objects[export.object_key]))
    names = archive.namelist()
    assert "manifest.json" in names
    assert len([name for name in names if name.endswith("prompt.txt")]) == 7
    assert not [name for name in names if name.endswith((".mp4", ".png"))]


def test_export_of_a_missing_campaign_is_a_404(service) -> None:
    with pytest.raises(UnknownCampaignError):
        service.export(f"ws-{uuid4().hex}", "missing")


def test_delivery_filenames_are_per_media() -> None:
    assert set(DELIVERY_FILENAMES) == {"video", "image"}


def test_the_manifest_json_is_ascii_clean(service, storage) -> None:
    ws = f"ws-{uuid4().hex}"
    bundle = service.create_from_briefing(ws, "coleção Legacy")
    export = service.export(ws, bundle.campaign.id)
    archive = zipfile.ZipFile(io.BytesIO(storage.objects[export.object_key]))
    manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
    assert manifest["campaign"]["primary_cta"]
