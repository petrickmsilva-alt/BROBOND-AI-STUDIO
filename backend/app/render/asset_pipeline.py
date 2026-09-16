"""PR008 — Asset Pipeline: every rendered scene is persisted automatically.

Per scene the pipeline saves, all through the existing `StorageService`
(the AssetStore — no new storage backend):

```text
main file    PNG (image) or MP4 (video)
thumbnail    PNG preview for images; playable copy for videos
metadata     JSON with prompt, seed and provider
```

`prompt`, `seed` and `provider` travel inside the metadata JSON and are also
echoed on the returned `RenderAsset`, so the Queue UI and the asset library
never have to open the file to show what produced it.

When a database session is supplied, one `Asset` row per file is created so
the library (`GET /api/v1/assets`) shows the render. Without it (unit tests),
only the stored files exist.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from ..core.contracts import GenerationKind
from ..providers.generation_executor import GenerationExecution

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids import cycles at runtime
    from sqlalchemy.orm import Session

    from ..storage import StorageService

THUMBNAIL_WIDTH_PX = 320
METADATA_KIND = "metadata"

IMAGE_CONTENT_TYPE = "image/png"
VIDEO_CONTENT_TYPE = "video/mp4"
METADATA_CONTENT_TYPE = "application/json"


@dataclass(frozen=True)
class RenderAsset:
    """Stored result of one rendered scene."""

    scene_id: str
    scene_number: int
    kind: str
    object_key: str
    url: str
    thumbnail_key: str
    thumbnail_url: str
    metadata_key: str
    metadata_url: str
    prompt: str
    seed: int | None
    provider_id: str
    spec_id: str
    width: int = 0
    height: int = 0
    duration_seconds: float = 0.0
    fps: int = 0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class RenderAssetPipeline:
    """Persists executor outputs through the AssetStore."""

    def __init__(self, storage: "StorageService | None" = None, staging_dir: str | Path | None = None) -> None:
        # Imported lazily so the module stays importable without settings.
        from ..storage import storage as default_storage

        self.storage = storage or default_storage
        self.staging_dir = Path(staging_dir) if staging_dir else None

    def persist(
        self,
        execution: GenerationExecution,
        *,
        workspace_id: str,
        batch_id: str,
        scene_id: str,
        scene_number: int,
        db: "Session | None" = None,
    ) -> RenderAsset:
        """Store main + thumbnail + metadata for one executed scene."""

        spec = execution.spec
        kind = spec.kind.value if isinstance(spec.kind, GenerationKind) else str(spec.kind)
        is_video = kind == GenerationKind.VIDEO.value
        suffix = "mp4" if is_video else "png"
        content_type = VIDEO_CONTENT_TYPE if is_video else IMAGE_CONTENT_TYPE

        base_name = f"scene-{scene_number:02d}-{spec.spec_id[:8]}"
        main_key, main_url = self._store_file(execution.asset.path, workspace_id, f"{base_name}.{suffix}", content_type)

        thumbnail_path = self._thumbnail_for(execution.asset.path, is_video=is_video)
        try:
            thumb_key, thumb_url = self._store_file(
                str(thumbnail_path), workspace_id, f"{base_name}-thumb.{suffix}", content_type
            )
        finally:
            if thumbnail_path != Path(execution.asset.path):
                thumbnail_path.unlink(missing_ok=True)

        metadata = self._metadata(execution, batch_id=batch_id, scene_id=scene_id, scene_number=scene_number, kind=kind)
        metadata_path = self._write_metadata(metadata, base_name)
        try:
            metadata_key, metadata_url = self._store_file(
                str(metadata_path), workspace_id, f"{base_name}.json", METADATA_CONTENT_TYPE
            )
        finally:
            metadata_path.unlink(missing_ok=True)

        asset = RenderAsset(
            scene_id=scene_id,
            scene_number=scene_number,
            kind=kind,
            object_key=main_key,
            url=main_url,
            thumbnail_key=thumb_key,
            thumbnail_url=thumb_url,
            metadata_key=metadata_key,
            metadata_url=metadata_url,
            prompt=spec.prompt_compiled,
            seed=spec.seed,
            provider_id=execution.asset.provider_id,
            spec_id=spec.spec_id,
            width=execution.asset.width,
            height=execution.asset.height,
            duration_seconds=execution.asset.duration_seconds,
            fps=execution.asset.fps,
        )
        if db is not None:
            self._record_rows(db, workspace_id=workspace_id, asset=asset, base_name=base_name)
        return asset

    # ------------------------------------------------------------------ files

    def _store_file(self, source: str, workspace_id: str, filename: str, content_type: str) -> tuple[str, str]:
        staged = self._stage(Path(source), filename)
        try:
            return self.storage.save_path(str(staged), workspace_id, content_type)
        finally:
            if staged != Path(source):
                staged.unlink(missing_ok=True)

    def _stage(self, source: Path, filename: str) -> Path:
        """Give the stored object a stable, scene-readable name.

        `save_path` mints `{workspace}/{uuid}-{filename}`: staging under the
        scene name keeps the key human-readable without changing the store.
        """

        if self.staging_dir is None:
            return source
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        staged = self.staging_dir / f"{uuid4().hex}-{filename}"
        staged.write_bytes(source.read_bytes())
        return staged

    def _thumbnail_for(self, asset_path: str, *, is_video: bool) -> Path:
        """Build a thumbnail file for the asset.

        Images are resized to a 320px preview when Pillow is importable,
        otherwise byte-copied. Videos are byte-copied: frame extraction needs
        an ffmpeg stage that does not exist yet (stated in RENDER_ENGINE.md),
        and a playable copy is an honest preview — the bytes are the render.
        """

        source = Path(asset_path)
        if is_video:
            return source
        try:
            from PIL import Image
        except ImportError:
            return source
        try:
            with Image.open(source) as image:
                image.load()
        except Exception:
            return source
        staging = self.staging_dir or source.parent
        staging.mkdir(parents=True, exist_ok=True)
        target = staging / f"{uuid4().hex}-thumb.png"
        with Image.open(source) as image:
            resized = image.convert("RGB")
            resized.thumbnail((THUMBNAIL_WIDTH_PX, THUMBNAIL_WIDTH_PX))
            resized.save(target, format="PNG")
        return target

    def _write_metadata(self, metadata: dict[str, Any], base_name: str) -> Path:
        staging = self.staging_dir or Path.cwd()
        staging.mkdir(parents=True, exist_ok=True)
        target = staging / f"{uuid4().hex}-{base_name}.json"
        target.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
        return target

    # ---------------------------------------------------------------- metadata

    @staticmethod
    def _metadata(
        execution: GenerationExecution, *, batch_id: str, scene_id: str, scene_number: int, kind: str
    ) -> dict[str, Any]:
        spec = execution.spec
        return {
            "batch_id": batch_id,
            "scene_id": scene_id,
            "scene_number": scene_number,
            "spec_id": spec.spec_id,
            "kind": kind,
            "prompt": spec.prompt_compiled,
            "prompt_original": spec.prompt_original,
            "negative_prompt": spec.negative_prompt,
            "seed": spec.seed,
            "provider": execution.asset.provider_id,
            "aspect_ratio": spec.aspect_ratio,
            "duration": spec.duration,
            "fps": spec.fps,
            "camera": spec.camera,
            "lens": spec.lens,
            "lighting": spec.lighting,
            "motion": spec.motion,
            "estimate": execution.job.estimate.to_dict(),
            "created_at": datetime.now(UTC).isoformat(),
        }

    # ------------------------------------------------------------------- rows

    @staticmethod
    def _record_rows(db: "Session", *, workspace_id: str, asset: RenderAsset, base_name: str) -> None:
        from ..models import Asset

        rows = [
            (f"{base_name}.{asset.object_key.rsplit('.', 1)[-1]}", asset.kind, asset.object_key),
            (f"{base_name}-thumb", asset.kind, asset.thumbnail_key),
            (f"{base_name}.json", METADATA_KIND, asset.metadata_key),
        ]
        for name, kind, object_key in rows:
            db.add(Asset(workspace_id=workspace_id, name=name, kind=kind, object_key=object_key))
        db.commit()
