"""V3.3 — Campaign Builder: persistence models.

Five tables hold one campaign's whole life, so a single briefing becomes a
complete, exportable campaign:

* ``campaigns`` — the campaign root: product, audience, platform, objective,
  status and the CTA seed that deterministically re-arms the CTA deck on
  duplication;
* ``campaign_briefs`` — the frozen ``CampaignBrief`` the Brief Interpreter
  produced from the raw briefing text, including the fields it could not
  find (``missing``) so the UI can be honest about defaults;
* ``campaign_episodes`` — one row per day of the campaign timeline
  (``BROBOND STUDIO V3 — MASTER ARCHITECTURE`` §V3.3: Dia 1..Dia 5), each
  with its own focus and CTA;
* ``campaign_assets`` — one row per deliverable (Reel 9:16, Story, Shorts,
  Banner, Thumbnail, Feed 1:1, YouTube Cover), carrying the generation
  prompt, the asset's own CTA and the delivered object keys. An asset is
  born ``planned`` and becomes ``delivered`` only when a real stored file
  is attached — the campaign never claims a render that does not exist;
* ``campaign_exports`` — one row per Export Center ZIP: object key, file
  count, checksum and the manifest that was packaged.

Conventions inherited from the codebase (``continuity_models`` V3.2):
``String(36)`` uuid primary keys, ``workspace_id`` as an indexed plain
reference (no DB-level foreign keys), naive-UTC timestamps, JSON documents
in ``Text`` columns — the same SQLite/Postgres-portable convention.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from .brief_interpreter import CampaignValidationError

#: Campaign lifecycle. A campaign is created ``active`` (the builder produces
#: a complete, ready-to-run plan) and only the API can retire it later.
CAMPAIGN_STATUSES: tuple[str, ...] = ("active", "paused", "completed")

#: Asset delivery states. ``delivered`` requires real stored files.
ASSET_STATUSES: tuple[str, ...] = ("planned", "delivered")

#: Media kinds a deliverable can have (video deliverables ship MP4,
#: image deliverables ship PNG — see ``export_center``).
MEDIA_KINDS: tuple[str, ...] = ("video", "image")


def dumps_payload(payload: dict) -> str:
    """Serialise a JSON document, rejecting non-JSON loudly."""

    if not isinstance(payload, dict):
        raise CampaignValidationError("payload must be an object")
    try:
        return json.dumps(payload, ensure_ascii=False)
    except (TypeError, ValueError) as error:
        raise CampaignValidationError(f"payload is not JSON-serialisable: {error}") from error


def loads_payload(raw: str | None) -> dict:
    """Parse a stored payload, defensively (a corrupt row reads as empty)."""

    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def utcnow() -> datetime:
    """Naive UTC timestamp, matching the repository convention."""

    return datetime.now(timezone.utc).replace(tzinfo=None)


def clean_text(value: object, field_name: str, *, max_length: int = 500) -> str:
    """Return the stripped string value, or raise when it is not a string."""

    if not isinstance(value, str):
        raise CampaignValidationError(f"{field_name} must be a string")
    cleaned = value.strip()
    if len(cleaned) > max_length:
        raise CampaignValidationError(f"{field_name} must be at most {max_length} characters")
    return cleaned


class Campaign(Base):
    """One campaign root, owned by exactly one workspace."""

    __tablename__ = "campaigns"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(160))
    product: Mapped[str] = mapped_column(String(160))
    product_type: Mapped[str] = mapped_column(String(80), default="")
    audience: Mapped[str] = mapped_column(String(160), default="")
    platform: Mapped[str] = mapped_column(String(80), default="")
    objective: Mapped[str] = mapped_column(String(40), default="")
    status: Mapped[str] = mapped_column(String(32), default="active")
    #: Drives the deterministic CTA deck; duplication mints a new seed so a
    #: copy never repeats its origin's CTA assignments.
    seed: Mapped[int] = mapped_column(Integer, default=0)
    primary_cta: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column()
    updated_at: Mapped[datetime] = mapped_column()


class CampaignBrief(Base):
    """The frozen interpretation of the raw briefing text (one per campaign)."""

    __tablename__ = "campaign_briefs"
    __table_args__ = (
        UniqueConstraint("workspace_id", "campaign_id", name="uq_campaign_briefs_campaign"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    campaign_id: Mapped[str] = mapped_column(String(36), index=True)
    raw_text: Mapped[str] = mapped_column(Text)
    product: Mapped[str] = mapped_column(String(160), default="")
    product_type: Mapped[str] = mapped_column(String(80), default="")
    audience: Mapped[str] = mapped_column(String(160), default="")
    platform: Mapped[str] = mapped_column(String(80), default="")
    objective: Mapped[str] = mapped_column(String(40), default="")
    duration_seconds: Mapped[int] = mapped_column(Integer, default=15)
    cta: Mapped[str] = mapped_column(String(200), default="")
    #: JSON arrays: which fields the interpreter had to default (``missing``)
    #: and which it actually read from the text (``matched``).
    missing_json: Mapped[str] = mapped_column(Text, default="[]")
    matched_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column()


class CampaignEpisode(Base):
    """One day of the campaign timeline (Dia 1..Dia 5)."""

    __tablename__ = "campaign_episodes"
    __table_args__ = (
        UniqueConstraint("workspace_id", "campaign_id", "day", name="uq_campaign_episodes_day"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    campaign_id: Mapped[str] = mapped_column(String(36), index=True)
    day: Mapped[int] = mapped_column(Integer)
    focus: Mapped[str] = mapped_column(String(120), default="")
    cta: Mapped[str] = mapped_column(String(200), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    #: JSON document: the deliverable kinds scheduled on this day.
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column()


class CampaignAsset(Base):
    """One deliverable of the campaign (Reel, Story, Shorts, Banner, ...)."""

    __tablename__ = "campaign_assets"
    __table_args__ = (
        UniqueConstraint("workspace_id", "campaign_id", "kind", name="uq_campaign_assets_kind"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    campaign_id: Mapped[str] = mapped_column(String(36), index=True)
    day: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    label: Mapped[str] = mapped_column(String(120), default="")
    medium: Mapped[str] = mapped_column(String(16), default="image")
    aspect_ratio: Mapped[str] = mapped_column(String(16), default="1:1")
    width: Mapped[int] = mapped_column(Integer, default=1080)
    height: Mapped[int] = mapped_column(Integer, default=1080)
    #: ``None`` for image deliverables (the spec's duration belongs to videos).
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt: Mapped[str] = mapped_column(Text, default="")
    cta: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(24), default="planned")
    output_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    thumbnail_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column()
    updated_at: Mapped[datetime] = mapped_column()


class CampaignExport(Base):
    """One Export Center ZIP: the campaign, packaged."""

    __tablename__ = "campaign_exports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    campaign_id: Mapped[str] = mapped_column(String(36), index=True)
    object_key: Mapped[str] = mapped_column(String(500))
    file_count: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(64), default="")
    manifest_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column()
