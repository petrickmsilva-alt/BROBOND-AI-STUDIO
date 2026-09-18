"""PR013 — V4.0.1: the wire model of one library entry.

Lives in this package (not `app/schemas.py`) so the Application Boundary
wires it with one import and the module keeps its own vocabulary. It is a
public model all the same: it is frozen into `docs/API_SNAPSHOT.json` by
`test_api_snapshot.py` like every other response shape.

Every nullable field uses ``None`` to mean *unknown*, never *zero* — the
rule the Quality Engine columns on `Asset` already follow.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from pydantic import BaseModel


class AssetLibraryEntryResponse(BaseModel):
    """What the Cinematic Asset Studio renders for one asset."""

    id: str
    name: str
    kind: str
    url: str
    created_at: datetime

    # Provenance of the row itself ---------------------------------------
    #: False for assets written before PR013 (or by other writers, e.g.
    #: renders): they stay visible with "—" fields instead of vanishing.
    has_metadata: bool
    source: str | None = None

    # The bytes -----------------------------------------------------------
    content_type: str | None = None
    size_bytes: int | None = None
    sha256: str | None = None
    resolution: str | None = None
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None

    # Thumbnail -----------------------------------------------------------
    thumbnail_url: str | None = None

    # Attribution (ETAPA 3's grid fields) --------------------------------
    project: str | None = None
    persona: str | None = None
    provider: str | None = None
    seed: int | None = None
    tags: list[str] = []

    # Quality verdict already denormalised on the Asset row (V3.4) -------
    quality_score: int | None = None
    quality_status: str | None = None
    quality_version: int | None = None

    # Before/After pairing (ETAPA 4 — prepared end to end) ---------------
    before_asset_id: str | None = None
    before_url: str | None = None
    before_thumbnail_url: str | None = None


def build_entry_response(
    record: "LibraryRecord",
    url_for: Callable[[str | None], str | None],
    *,
    before: "LibraryRecord | None" = None,
) -> AssetLibraryEntryResponse:
    """Assemble the wire model for one record.

    `url_for` resolves a stored object key to an access URL (the
    `StorageService` signed/local adapter deal); it is injected so the
    mapping stays a pure, testable function with no storage client of its
    own. `before` is the paired record when a before/after pair exists and
    belongs to the same workspace; ``None`` keeps every before field
    ``None`` rather than leaking another tenant's URL.
    """

    # Imported here to avoid a schema -> service import cycle at module
    # load; typing is satisfied by the quoted annotations above.
    from .library_service import LibraryRecord  # noqa: F401

    metadata = record.metadata

    def _text(value: str | None) -> str | None:
        """Collapse empty strings to None — unknown, never zero."""
        return value or None

    return AssetLibraryEntryResponse(
        id=record.asset.id,
        name=record.asset.name,
        kind=record.asset.kind,
        url=url_for(record.asset.object_key) or "",
        created_at=record.asset.created_at,
        has_metadata=record.has_metadata,
        source=_text(metadata.source) if metadata is not None else None,
        content_type=metadata.content_type if metadata is not None else None,
        size_bytes=metadata.size_bytes if metadata is not None else None,
        sha256=metadata.sha256 if metadata is not None else None,
        resolution=record.resolution,
        width=metadata.width if metadata is not None else None,
        height=metadata.height if metadata is not None else None,
        duration_seconds=metadata.duration_seconds if metadata is not None else None,
        thumbnail_url=url_for(metadata.thumbnail_key) if metadata is not None else None,
        project=_text(metadata.project) if metadata is not None else None,
        persona=_text(metadata.persona) if metadata is not None else None,
        provider=_text(metadata.provider) if metadata is not None else None,
        seed=metadata.seed if metadata is not None else None,
        tags=list(record.tags),
        quality_score=record.asset.quality_score,
        quality_status=record.asset.quality_status,
        quality_version=record.asset.quality_version,
        before_asset_id=metadata.before_asset_id if metadata is not None else None,
        before_url=url_for(before.asset.object_key) if before is not None else None,
        before_thumbnail_url=url_for(before.metadata.thumbnail_key)
        if before is not None and before.metadata is not None
        else None,
    )
