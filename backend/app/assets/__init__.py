"""PR013 — V4.0.1 Cinematic Asset Studio: the Asset Library module.

What exists before this package: `POST /api/v1/assets/upload` stores bytes
through `StorageService` and writes a bare `Asset` row (workspace, name,
kind, object key). That is enough to *keep* a file, but not to run a
professional library on it — there is no thumbnail, no size, no sha, no
resolution, no project/persona/provider attribution and nothing to filter
or search by.

This package adds exactly that layer, and nothing else:

* `library_models`     — `AssetMetadata`: the 1:1 companion row of an
  `Asset` holding everything the library grid shows (thumbnail key,
  content type, byte size, sha256, resolution, duration, project, persona,
  provider, seed, tags and the before/after pairing);
* `thumbnails`         — Pillow-based image probing and thumbnail
  rendering, deliberately honest: no thumbnail is ever *claimed* for a
  video (decoding MP4/MOV needs ffmpeg, which LIMITATIONS.md lists as
  absent), so video entries carry `thumbnail_key = NULL` and the UI shows
  a film tile instead of an invented frame;
* `library_service`    — the ingest pipeline (validate → store via the
  existing `StorageService` → thumbnail → `Asset` + `AssetMetadata` in one
  transaction) plus the filtered/searched reads the library and the
  preview drawer consume;
* `library_schemas`    — the wire model `AssetLibraryEntryResponse`.

Boundary (docs/ARCHITECTURE_MANIFEST.md): the module may know Persistence
(`app.db`, `app.models`) and Storage (`app.storage`) — nothing else. It
never imports Provider Registry, Render Engine, Director AI or the Prompt
Compiler; generated assets keep flowing in through their own writers, and
this package only *reads* them back out.
"""

from .library_models import AssetMetadata
from .library_schemas import AssetLibraryEntryResponse
from .library_service import (
    ACCEPTED_CONTENT_TYPES,
    LibraryFilters,
    LibraryRecord,
    asset_library,
    parse_tags,
)
from .thumbnails import build_image_thumbnail, probe_image

__all__ = [
    "ACCEPTED_CONTENT_TYPES",
    "AssetLibraryEntryResponse",
    "AssetMetadata",
    "LibraryFilters",
    "LibraryRecord",
    "asset_library",
    "build_image_thumbnail",
    "parse_tags",
    "probe_image",
]
