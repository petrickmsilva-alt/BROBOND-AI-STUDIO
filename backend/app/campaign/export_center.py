"""V3.3 — Export Center: one briefing's whole campaign in one ZIP.

``build_manifest`` and ``build_zip`` package a campaign for delivery:

* ``manifest.json`` — the Campaign Manifest: campaign, brief, five-day
  timeline, every asset with prompt/CTA/format and the export's entry list;
* per asset ``{day:02d}-{kind}/`` — ``prompt.txt`` (the generation prompt)
  and ``metadata.json`` (the full asset record);
* for every *delivered* asset — real stored files — the binary itself:
  ``delivery.mp4`` for video media, ``delivery.png`` for image media, plus
  ``thumbnail.png`` when a thumbnail was attached.

The rule the whole repository lives by applies to the ZIP too: nothing is
invented. An asset still waiting on the render engine contributes its
prompt and metadata, never a fake binary. Framework-free: stdlib
``zipfile``/``json``/``hashlib`` only; persistence goes through the
storage adapter in the campaign service.
"""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from dataclasses import dataclass
from typing import Mapping

from .brief_interpreter import CampaignValidationError

#: Manifest contract version, so a downloaded ZIP can be validated later.
MANIFEST_VERSION = 1

#: Binary file name per media kind inside an asset's folder.
DELIVERY_FILENAMES: dict[str, str] = {"video": "delivery.mp4", "image": "delivery.png"}
THUMBNAIL_FILENAME = "thumbnail.png"

MANIFEST_FILENAME = "manifest.json"


def asset_folder(asset: Mapping[str, object]) -> str:
    """Stable per-asset folder: ``01-reel``, ``03-cover``, ..."""

    day = asset.get("day")
    kind = str(asset.get("kind") or "asset")
    day_token = f"{int(day):02d}" if isinstance(day, int) else "00"
    return f"{day_token}-{kind}"


def build_manifest(
    campaign: Mapping[str, object],
    brief: Mapping[str, object],
    assets: list[Mapping[str, object]],
    episodes: list[Mapping[str, object]],
) -> dict[str, object]:
    """The Campaign Manifest: everything a recipient needs to know."""

    return {
        "manifest_version": MANIFEST_VERSION,
        "campaign": dict(campaign),
        "brief": dict(brief),
        "timeline": [dict(episode) for episode in episodes],
        "assets": [dict(asset) for asset in assets],
    }


def asset_entries(asset: Mapping[str, object]) -> list[tuple[str, bytes]]:
    """The text entries one asset contributes: prompt + metadata."""

    folder = asset_folder(asset)
    prompt = str(asset.get("prompt") or "")
    metadata = json.dumps(dict(asset), ensure_ascii=False, indent=2, sort_keys=True)
    return [
        (f"{folder}/prompt.txt", prompt.encode("utf-8")),
        (f"{folder}/metadata.json", metadata.encode("utf-8")),
    ]


def build_zip(
    manifest: Mapping[str, object],
    assets: list[Mapping[str, object]],
    binaries: Mapping[str, bytes] | None = None,
) -> "ExportPackage":
    """Package the campaign into one deterministic ZIP.

    ``binaries`` maps archive paths (``01-reel/delivery.mp4``) to real
    bytes; the caller (campaign service) reads them through the storage
    adapter and only passes keys that actually exist. Entry order is
    sorted, so the same campaign always packages to the same bytes.
    """

    entries: list[tuple[str, bytes]] = [
        (MANIFEST_FILENAME, json.dumps(dict(manifest), ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")),
    ]
    for asset in assets:
        entries.extend(asset_entries(asset))
    for path, payload in sorted((binaries or {}).items()):
        if not isinstance(payload, (bytes, bytearray)):
            raise CampaignValidationError(f"binary payload for {path} must be bytes")
        entries.append((path, bytes(payload)))

    names = [name for name, _ in entries]
    if len(set(names)) != len(names):
        raise CampaignValidationError("export entries must not collide")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in sorted(entries, key=lambda entry: entry[0]):
            archive.writestr(name, payload)
    data = buffer.getvalue()
    return ExportPackage(
        data=data,
        entries=sorted(names),
        file_count=len(names),
        sha256=hashlib.sha256(data).hexdigest(),
    )


@dataclass(frozen=True)
class ExportPackage:
    """One built ZIP: bytes, the entry list and the checksum."""

    data: bytes
    entries: tuple[str, ...]
    file_count: int
    sha256: str


def read_manifest(package: bytes) -> dict[str, object]:
    """Read the manifest back out of a built ZIP (the tests' round-trip)."""

    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        return json.loads(archive.read(MANIFEST_FILENAME).decode("utf-8"))
