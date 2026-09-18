"""PR013 — V4.0.1: persistence for the Cinematic Asset Studio.

One table, `asset_metadata`, the 1:1 companion of `assets`. The `assets`
row itself is shared infrastructure (uploads, renders, conditioning,
exports all write it) and PR013 must not change any of those flows, so the
library's own facts live here, keyed by `asset_id` and scoped by
`workspace_id` exactly like every tenant table in the platform.

Convention notes that matter to reviewers:

* nullable means *unknown*, never *zero*. A video whose resolution was not
  probed has `width = NULL` — the UI renders "—", not a made-up number;
* `tags` is a JSON document in a Text column, the same SQLite/Postgres
  portable convention `persona_wardrobe.metadata` and `audit_log.detail`
  already use;
* `before_asset_id` is intentionally *not* a database foreign key — the
  paired asset may live in the same upload batch and may be deleted
  independently, matching the repo's "no DB-level FK between product
  tables" convention (`persona_images.asset_id` does the same).
"""
from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class AssetMetadata(Base):
    """The library card of one asset: everything the grid shows that the
    bare `assets.assets` row does not carry."""

    __tablename__ = "asset_metadata"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    asset_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)

    # What the bytes are -------------------------------------------------
    content_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column()
    sha256: Mapped[str] = mapped_column(String(64))
    width: Mapped[int | None] = mapped_column(nullable=True)
    height: Mapped[int | None] = mapped_column(nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(nullable=True)
    thumbnail_key: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Who made it --------------------------------------------------------
    project: Mapped[str] = mapped_column(String(160), default="")
    persona: Mapped[str] = mapped_column(String(160), default="")
    provider: Mapped[str] = mapped_column(String(80), default="upload")
    seed: Mapped[int | None] = mapped_column(nullable=True)
    tags_json: Mapped[str] = mapped_column("tags", Text, default="[]")
    #: Where the row came from: uploads minted by this module say "upload".
    #: Future writers (a render bridge, an import job) must choose their
    #: own value so the library can badge provenance honestly.
    source: Mapped[str] = mapped_column(String(32), default="upload")

    # Before/After preparation ------------------------------------------
    before_asset_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
