"""PR013 — V4.0.1: ingest, filtered reads and the library record.

The pipeline, in words:

```text
UploadFile (multipart) -> accept-list check (PNG/JPG/WEBP/MP4/MOV)
  -> read bytes once -> sha256 + size
  -> StorageService.save (the existing adapter, local or MinIO)
  -> Pillow probe + thumbnail (images only; honest NULLs for video)
  -> Asset row + AssetMetadata row in one transaction
```

Why `UploadFile` objects are rebuilt around the in-memory bytes before
calling `storage.save`: the service needs the bytes *anyway* (sha256,
dimensions, thumbnail), and the existing `StorageService` contract is an
`UploadFile` — rebuilding keeps that contract untouched instead of adding
a parallel write path to storage. Nothing in `app/storage.py` changes.

Reads are deliberately tolerant of history: every `Asset` ever written
before PR013 (renders, conditioning, legacy uploads) has no
`AssetMetadata` row. The LEFT JOIN keeps them all visible in the library
with `has_metadata = False` and NULL-derived fields rendered as "—", so
adopting V4.0.1 never empties an existing library.
"""
from __future__ import annotations

import hashlib
import io
import json
from dataclasses import dataclass, field
from datetime import datetime

from fastapi import HTTPException, UploadFile
from fastapi.datastructures import Headers
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Asset
from ..storage import StorageService
from ..storage import storage as default_storage
from .library_models import AssetMetadata
from .thumbnails import build_image_thumbnail, probe_image

#: ETAPA 1's accept-list, mirrored from the Upload Engine: PNG, JPG, WEBP,
#: MP4 and MOV. Anything else is a 415, never a silent rename of the kind.
ACCEPTED_CONTENT_TYPES: dict[str, str] = {
    "image/png": "image",
    "image/jpeg": "image",
    "image/webp": "image",
    "video/mp4": "video",
    "video/quicktime": "video",
}

#: Extension fallback for browsers that report no MIME (some report `""`
#: for `.mov`). Matched lowercase, without the dot.
ACCEPTED_EXTENSIONS: dict[str, str] = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "mp4": "video/mp4",
    "mov": "video/quicktime",
}

#: A single upload is bounded so a stray 4 GB drop cannot stream straight
#: into the media root. 512 MB covers any still and short cinematic clips;
#: bigger deliverables belong in the render/export flow, not the drop zone.
MAX_UPLOAD_BYTES = 512 * 1024 * 1024


def parse_tags(raw: str | None) -> list[str]:
    """Normalise the multipart `tags` field into a clean, deduped list.

    Accepts a comma-separated string (`"editorial, dusk"`). Empty pieces
    are dropped, order is kept, repeats collapse. The stored JSON is built
    from exactly this list, so the search index and the response always
    agree.
    """

    if not raw:
        return []
    seen: list[str] = []
    for piece in raw.split(","):
        tag = " ".join(piece.strip().lower().split())
        if tag and tag not in seen:
            seen.append(tag)
    return seen


def resolve_content_type(content_type: str | None, filename: str | None) -> str | None:
    """The effective MIME of the upload, with the extension as fallback.

    Browsers occasionally send an empty or generic type for `.mov`; the
    extension resolves those honestly. Returns ``None`` when neither says
    anything usable — the route turns that into the same 415 as an
    unsupported type.
    """

    if content_type and content_type in ACCEPTED_CONTENT_TYPES:
        return content_type
    if filename and "." in filename:
        suffix = filename.rsplit(".", 1)[1].strip().lower()
        if suffix in ACCEPTED_EXTENSIONS:
            return ACCEPTED_EXTENSIONS[suffix]
    return None


@dataclass(frozen=True)
class LibraryFilters:
    """The ETAPA 5 filter set. ``None`` means "no filter", never a wildcard
    the caller must guess at."""

    kind: str | None = None
    project: str | None = None
    persona: str | None = None
    provider: str | None = None
    min_score: int | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    query: str | None = None


@dataclass(frozen=True)
class LibraryRecord:
    """One library row: the `Asset` joined with its optional metadata."""

    asset: Asset
    metadata: AssetMetadata | None = None
    tags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def has_metadata(self) -> bool:
        return self.metadata is not None

    @property
    def resolution(self) -> str | None:
        if self.metadata is None or not self.metadata.width or not self.metadata.height:
            return None
        return f"{self.metadata.width}×{self.metadata.height}"


def _metadata_tags(metadata: AssetMetadata | None) -> tuple[str, ...]:
    if metadata is None:
        return ()
    try:
        raw = json.loads(metadata.tags_json or "[]")
    except (TypeError, ValueError):
        return ()
    return tuple(str(tag) for tag in raw if str(tag).strip())


def _to_record(asset: Asset, metadata: AssetMetadata | None) -> LibraryRecord:
    return LibraryRecord(asset=asset, metadata=metadata, tags=_metadata_tags(metadata))


class AssetLibraryService:
    """Ingest and read the library. Storage goes through the injected
    adapter — the module default is the platform's existing service."""

    def __init__(self, storage_service: StorageService | None = None) -> None:
        self.storage = storage_service or default_storage

    # ------------------------------------------------------------- ingest

    async def ingest(
        self,
        db: Session,
        workspace_id: str,
        *,
        file: UploadFile,
        project: str = "",
        persona: str = "",
        provider: str = "upload",
        seed: int | None = None,
        tags: list[str] | tuple[str, ...] = (),
        before_asset_id: str | None = None,
    ) -> LibraryRecord:
        """Store one upload: bytes + thumbnail + Asset + AssetMetadata.

        Raises HTTPException 415 (unsupported type), 413 (too large) or
        422 (empty body / unknown pairing); the route layer stays thin.
        """

        content_type = resolve_content_type(file.content_type, file.filename)
        if content_type is None:
            raise HTTPException(status_code=415, detail="Unsupported file type — upload PNG, JPG, WEBP, MP4 or MOV")
        kind = ACCEPTED_CONTENT_TYPES[content_type]

        data = await file.read()
        if not data:
            raise HTTPException(status_code=422, detail="Empty file")
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail=f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB upload limit")

        if before_asset_id is not None:
            paired = db.get(Asset, before_asset_id)
            if paired is None or paired.workspace_id != workspace_id:
                raise HTTPException(status_code=422, detail="before_asset_id does not reference an existing asset")

        digest = hashlib.sha256(data).hexdigest()

        # Main bytes, through the untouched StorageService contract.
        stored = UploadFile(
            file=io.BytesIO(data),
            filename=file.filename or f"upload.{_extension_for(content_type)}",
            headers=Headers({"content-type": content_type}),
        )
        object_key, _ = await self.storage.save(stored, workspace_id)

        # Probe + thumbnail. Images only — see thumbnails.py's honesty rule.
        width: int | None = None
        height: int | None = None
        thumbnail_key: str | None = None
        if kind == "image":
            probe = probe_image(data)
            if probe is not None:
                width, height = probe.width, probe.height
            thumbnail_bytes = build_image_thumbnail(data)
            if thumbnail_bytes is not None:
                thumbnail_upload = UploadFile(
                    file=io.BytesIO(thumbnail_bytes),
                    filename=f"{_stem(file.filename)}.thumb.png",
                    headers=Headers({"content-type": "image/png"}),
                )
                thumbnail_key, _ = await self.storage.save(thumbnail_upload, workspace_id)

        asset = Asset(
            workspace_id=workspace_id,
            name=file.filename or f"upload.{_extension_for(content_type)}",
            kind=kind,
            object_key=object_key,
        )
        db.add(asset)
        db.flush()  # asset.id is minted inside the same transaction

        metadata = AssetMetadata(
            asset_id=asset.id,
            workspace_id=workspace_id,
            content_type=content_type,
            size_bytes=len(data),
            sha256=digest,
            width=width,
            height=height,
            thumbnail_key=thumbnail_key,
            project=project.strip(),
            persona=persona.strip(),
            provider=provider.strip() or "upload",
            seed=seed,
            tags_json=json.dumps(list(tags), ensure_ascii=False),
            source="upload",
            before_asset_id=before_asset_id,
        )
        db.add(metadata)
        db.commit()
        db.refresh(asset)
        db.refresh(metadata)
        return _to_record(asset, metadata)

    # -------------------------------------------------------------- reads

    def list_records(self, db: Session, workspace_id: str, filters: LibraryFilters | None = None) -> list[LibraryRecord]:
        """Every asset of the workspace, metadata LEFT JOINed, filtered.

        Filtering happens in Python, not SQL, on purpose: the library is a
        workspace-scoped view (hundreds of rows, not millions), the tags
        document is JSON text, and keeping the predicates here means they
        are unit-testable without a database dialect matrix. The join +
        ordering stay in SQL.
        """

        filters = filters or LibraryFilters()
        rows = db.execute(
            select(Asset, AssetMetadata)
            .outerjoin(
                AssetMetadata,
                (AssetMetadata.asset_id == Asset.id) & (AssetMetadata.workspace_id == Asset.workspace_id),
            )
            .where(Asset.workspace_id == workspace_id)
            .order_by(Asset.created_at.desc(), Asset.id.desc())
        ).all()
        records = [_to_record(asset, metadata) for asset, metadata in rows]
        return [record for record in records if _matches(record, filters)]

    def get_record(self, db: Session, workspace_id: str, asset_id: str) -> LibraryRecord | None:
        asset = db.get(Asset, asset_id)
        if asset is None or asset.workspace_id != workspace_id:
            return None
        metadata = db.scalar(select(AssetMetadata).where(AssetMetadata.asset_id == asset.id, AssetMetadata.workspace_id == workspace_id))
        return _to_record(asset, metadata)

    # ---------------------------------------------------------------- urls

    def url_for(self, object_key: str | None) -> str | None:
        if not object_key:
            return None
        return self.storage.signed_url(object_key)


def _matches(record: LibraryRecord, filters: LibraryFilters) -> bool:
    """One row against the full filter set. Every predicate short-circuits
    on "no filter", and every comparison is case-insensitive so the UI can
    render exactly what the operator typed without a normalisation dance."""

    if filters.kind and record.asset.kind != filters.kind:
        return False
    if filters.project and (record.metadata is None or record.metadata.project.lower() != filters.project.lower()):
        return False
    if filters.persona and (record.metadata is None or record.metadata.persona.lower() != filters.persona.lower()):
        return False
    if filters.provider and (record.metadata is None or record.metadata.provider.lower() != filters.provider.lower()):
        return False
    if filters.min_score is not None and (record.asset.quality_score is None or record.asset.quality_score < filters.min_score):
        return False
    if filters.date_from and record.asset.created_at < filters.date_from:
        return False
    if filters.date_to and record.asset.created_at > filters.date_to:
        return False
    if filters.query:
        needle = filters.query.strip().lower()
        if needle:
            haystack = " ".join([record.asset.name, record.asset.kind, *record.tags]).lower()
            if needle not in haystack:
                return False
    return True


def _stem(filename: str | None) -> str:
    name = (filename or "upload").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    stem, dot, _ = name.rpartition(".")
    return stem if dot else name


def _extension_for(content_type: str) -> str:
    return {
        "image/png": "png",
        "image/jpeg": "jpg",
        "image/webp": "webp",
        "video/mp4": "mp4",
        "video/quicktime": "mov",
    }[content_type]


asset_library = AssetLibraryService()
