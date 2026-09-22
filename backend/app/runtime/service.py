"""Application bridge from runtime artifacts to the existing Asset Library."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from ..assets.library_models import AssetMetadata
from ..models import Asset
from ..storage import storage

# Stable internal render state names. The persisted Job contract continues to
# expose queued/running/completed/failed; these states travel as optional
# metadata on the existing progress event.
RUNTIME_STATES: tuple[str, ...] = (
    "queued",
    "loading_model",
    "generating",
    "encoding",
    "completed",
    "failed",
)


@dataclass(frozen=True)
class PersistedRuntimeAsset:
    id: str
    url: str
    kind: str
    model: str
    object_key: str


def persist_runtime_asset(
    db: Session,
    *,
    source_path: str | Path,
    workspace_id: str,
    kind: str,
    model: str,
    prompt: str,
    seed: int | None,
    width: int,
    height: int,
    duration: float | None = None,
    fps: int | None = None,
) -> PersistedRuntimeAsset:
    """Write a generated file and its library metadata in one DB transaction.

    The pre-existing Asset/AssetMetadata schema has no prompt column by design;
    the prompt is therefore retained as a searchable provenance tag while the
    model, dimensions, seed and generation date use their typed library fields.
    No new database table or authentication contract is introduced here.
    """

    source = Path(source_path)
    if not source.is_file():
        raise FileNotFoundError(f"runtime output does not exist: {source}")
    extension = "png" if kind == "image" else "mp4"
    content_type = "image/png" if kind == "image" else "video/mp4"
    object_key, url = storage.save_path(str(source), workspace_id, content_type)
    data = source.read_bytes()
    tags = [f"model:{model}", f"prompt:{prompt}"]
    if fps is not None:
        tags.append(f"fps:{fps}")

    asset = Asset(
        workspace_id=workspace_id,
        name=f"{model}-{source.stem}.{extension}",
        kind=kind,
        object_key=object_key,
    )
    db.add(asset)
    db.flush()
    metadata = AssetMetadata(
        asset_id=asset.id,
        workspace_id=workspace_id,
        content_type=content_type,
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        width=width,
        height=height,
        duration_seconds=duration,
        project="",
        persona="",
        provider=model,
        seed=seed,
        tags_json=json.dumps(tags, ensure_ascii=False),
        source="runtime",
    )
    db.add(metadata)
    db.commit()
    db.refresh(asset)
    return PersistedRuntimeAsset(
        id=asset.id,
        url=url,
        kind=kind,
        model=model,
        object_key=object_key,
    )


__all__ = ["PersistedRuntimeAsset", "RUNTIME_STATES", "persist_runtime_asset"]
