"""V3.3: repository over the campaign tables.

The single persistence boundary for the Campaign Builder, following the
convention ``continuity/continuity_repository.py`` (V3.2) established:

* short-lived ``SessionLocal`` sessions per call, detached views before the
  session closes, module-level ``campaign_repo`` singleton for the API;
* every read and write is workspace-scoped — a foreign id behaves as a 404,
  never a 403, so tenant ids are not enumerable;
* ``create_campaign`` writes the whole bundle (root + brief + assets +
  episodes) in one transaction: a campaign is born complete or not at all;
* ``deliver_asset`` is the only mutation of an asset after creation (the
  planned → delivered transition with real object keys).
"""
from __future__ import annotations

import json
from uuid import uuid4
from dataclasses import dataclass, field
from typing import Mapping, Sequence

from sqlalchemy import select

from ..db import SessionLocal
from .brief_interpreter import CampaignValidationError
from .campaign_models import (
    Campaign,
    CampaignAsset,
    CampaignBrief,
    CampaignEpisode,
    CampaignExport,
    clean_text,
    dumps_payload,
    loads_payload,
    utcnow,
)


class CampaignRepositoryError(Exception):
    """Raised when a write cannot proceed (duplicate deliverable kind)."""


@dataclass(frozen=True)
class CampaignView:
    """A detached campaign root."""

    id: str
    workspace_id: str
    name: str
    product: str
    product_type: str = ""
    audience: str = ""
    platform: str = ""
    objective: str = ""
    status: str = "active"
    seed: int = 0
    primary_cta: str = ""
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "name": self.name,
            "product": self.product,
            "product_type": self.product_type,
            "audience": self.audience,
            "platform": self.platform,
            "objective": self.objective,
            "status": self.status,
            "seed": self.seed,
            "primary_cta": self.primary_cta,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class CampaignBriefView:
    """A detached frozen brief."""

    id: str
    workspace_id: str
    campaign_id: str
    raw_text: str
    product: str = ""
    product_type: str = ""
    audience: str = ""
    platform: str = ""
    objective: str = ""
    duration_seconds: int = 15
    cta: str = ""
    missing: tuple[str, ...] = ()
    matched: tuple[str, ...] = ()
    created_at: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "campaign_id": self.campaign_id,
            "raw_text": self.raw_text,
            "product": self.product,
            "product_type": self.product_type,
            "audience": self.audience,
            "platform": self.platform,
            "objective": self.objective,
            "duration_seconds": self.duration_seconds,
            "cta": self.cta,
            "missing": list(self.missing),
            "matched": list(self.matched),
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class CampaignAssetView:
    """A detached deliverable: format, day, prompt, CTA and delivery state."""

    id: str
    workspace_id: str
    campaign_id: str
    day: int
    kind: str
    label: str = ""
    medium: str = "image"
    aspect_ratio: str = "1:1"
    width: int = 1080
    height: int = 1080
    duration_seconds: int | None = None
    prompt: str = ""
    cta: str = ""
    status: str = "planned"
    output_key: str | None = None
    thumbnail_key: str | None = None
    position: int = 0
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "campaign_id": self.campaign_id,
            "day": self.day,
            "kind": self.kind,
            "label": self.label,
            "medium": self.medium,
            "aspect_ratio": self.aspect_ratio,
            "width": self.width,
            "height": self.height,
            "duration_seconds": self.duration_seconds,
            "prompt": self.prompt,
            "cta": self.cta,
            "status": self.status,
            "output_key": self.output_key,
            "thumbnail_key": self.thumbnail_key,
            "position": self.position,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class CampaignEpisodeView:
    """A detached timeline day."""

    id: str
    workspace_id: str
    campaign_id: str
    day: int
    focus: str = ""
    cta: str = ""
    notes: str = ""
    asset_kinds: tuple[str, ...] = field(default=())
    created_at: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "campaign_id": self.campaign_id,
            "day": self.day,
            "focus": self.focus,
            "cta": self.cta,
            "notes": self.notes,
            "asset_kinds": list(self.asset_kinds),
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class CampaignExportView:
    """A detached export record."""

    id: str
    workspace_id: str
    campaign_id: str
    object_key: str
    file_count: int = 0
    sha256: str = ""
    manifest: Mapping[str, object] = field(default_factory=dict)
    created_at: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "campaign_id": self.campaign_id,
            "object_key": self.object_key,
            "file_count": self.file_count,
            "sha256": self.sha256,
            "manifest": dict(self.manifest),
            "created_at": self.created_at,
        }


def _campaign_view(row: Campaign) -> CampaignView:
    return CampaignView(
        id=row.id,
        workspace_id=row.workspace_id,
        name=row.name,
        product=row.product,
        product_type=row.product_type,
        audience=row.audience,
        platform=row.platform,
        objective=row.objective,
        status=row.status,
        seed=row.seed,
        primary_cta=row.primary_cta,
        created_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
    )


def _brief_view(row: CampaignBrief) -> CampaignBriefView:
    return CampaignBriefView(
        id=row.id,
        workspace_id=row.workspace_id,
        campaign_id=row.campaign_id,
        raw_text=row.raw_text,
        product=row.product,
        product_type=row.product_type,
        audience=row.audience,
        platform=row.platform,
        objective=row.objective,
        duration_seconds=row.duration_seconds,
        cta=row.cta,
        missing=tuple(loads_array(row.missing_json)),
        matched=tuple(loads_array(row.matched_json)),
        created_at=row.created_at.isoformat(),
    )


def _asset_view(row: CampaignAsset) -> CampaignAssetView:
    return CampaignAssetView(
        id=row.id,
        workspace_id=row.workspace_id,
        campaign_id=row.campaign_id,
        day=row.day,
        kind=row.kind,
        label=row.label,
        medium=row.medium,
        aspect_ratio=row.aspect_ratio,
        width=row.width,
        height=row.height,
        duration_seconds=row.duration_seconds,
        prompt=row.prompt,
        cta=row.cta,
        status=row.status,
        output_key=row.output_key,
        thumbnail_key=row.thumbnail_key,
        position=row.position,
        created_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
    )


def _episode_view(row: CampaignEpisode) -> CampaignEpisodeView:
    payload = loads_payload(row.payload_json)
    kinds = payload.get("asset_kinds", [])
    return CampaignEpisodeView(
        id=row.id,
        workspace_id=row.workspace_id,
        campaign_id=row.campaign_id,
        day=row.day,
        focus=row.focus,
        cta=row.cta,
        notes=row.notes,
        asset_kinds=tuple(kinds) if isinstance(kinds, list) else (),
        created_at=row.created_at.isoformat(),
    )


def _export_view(row: CampaignExport) -> CampaignExportView:
    return CampaignExportView(
        id=row.id,
        workspace_id=row.workspace_id,
        campaign_id=row.campaign_id,
        object_key=row.object_key,
        file_count=row.file_count,
        sha256=row.sha256,
        manifest=loads_payload(row.manifest_json),
        created_at=row.created_at.isoformat(),
    )


def dumps_array(values: Sequence[str]) -> str:
    """Serialise the brief's missing/matched tuples as a JSON array."""

    if not isinstance(values, (list, tuple, set)):
        raise CampaignValidationError("field list must be a sequence of strings")
    items = list(values)
    if not all(isinstance(item, str) for item in items):
        raise CampaignValidationError("field list must contain only strings")
    return json.dumps(items, ensure_ascii=False)


def loads_array(raw: str | None) -> list[str]:
    """Parse a stored field list, defensively."""

    try:
        value = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


@dataclass(frozen=True)
class CampaignBundle:
    """Everything one created (or duplicated) campaign owns."""

    campaign: CampaignView
    brief: CampaignBriefView
    assets: tuple[CampaignAssetView, ...]
    episodes: tuple[CampaignEpisodeView, ...]


class CampaignRepository:
    """Transactional bundle writes, workspace-scoped reads."""

    # ------------------------------------------------------------------ write

    def create_campaign(
        self,
        workspace_id: str,
        *,
        campaign: Mapping[str, object],
        brief: Mapping[str, object],
        assets: Sequence[Mapping[str, object]],
        episodes: Sequence[Mapping[str, object]],
    ) -> CampaignBundle:
        """Write the whole campaign bundle in one transaction.

        A campaign is born complete — root, brief, seven assets and five
        days commit together or not at all. Duplicate deliverable kinds are
        refused: the plan is one asset per format.
        """

        root = self._campaign_row(workspace_id, campaign)
        #: The root's uuid default fires at flush time; children need the id
        # now, so the campaign id is minted eagerly and passed down.
        root.id = root.id or str(uuid4())
        brief_row = self._brief_row(workspace_id, root.id, brief)
        asset_rows = [self._asset_row(workspace_id, root.id, asset) for asset in assets]
        episode_rows = [self._episode_row(workspace_id, root.id, episode) for episode in episodes]
        kinds = [row.kind for row in asset_rows]
        if len(set(kinds)) != len(kinds):
            raise CampaignRepositoryError("a campaign carries each deliverable kind exactly once")
        days = [row.day for row in episode_rows]
        if len(set(days)) != len(days):
            raise CampaignRepositoryError("a timeline carries each day exactly once")
        with SessionLocal() as db:
            db.add_all([root, brief_row, *asset_rows, *episode_rows])
            db.commit()
            db.refresh(root)
            db.refresh(brief_row)
            for row in (*asset_rows, *episode_rows):
                db.refresh(row)
            bundle = CampaignBundle(
                campaign=_campaign_view(root),
                brief=_brief_view(brief_row),
                assets=tuple(_asset_view(row) for row in asset_rows),
                episodes=tuple(_episode_view(row) for row in episode_rows),
            )
            for row in (root, brief_row, *asset_rows, *episode_rows):
                db.expunge(row)
            return bundle

    def deliver_asset(
        self,
        workspace_id: str,
        campaign_id: str,
        asset_id: str,
        *,
        output_key: str | None,
        thumbnail_key: str | None,
    ) -> CampaignAssetView | None:
        """Attach delivered files to one asset (planned → delivered)."""

        cleaned_output = self._optional_key(output_key, "output_key")
        cleaned_thumbnail = self._optional_key(thumbnail_key, "thumbnail_key")
        with SessionLocal() as db:
            row = db.scalar(
                select(CampaignAsset).where(
                    CampaignAsset.workspace_id == workspace_id,
                    CampaignAsset.campaign_id == campaign_id,
                    CampaignAsset.id == asset_id,
                )
            )
            if row is None:
                return None
            if cleaned_output is not None:
                row.output_key = cleaned_output
            if cleaned_thumbnail is not None:
                row.thumbnail_key = cleaned_thumbnail
            row.status = "delivered" if row.output_key else row.status
            row.updated_at = utcnow()
            db.commit()
            db.refresh(row)
            view = _asset_view(row)
            db.expunge(row)
            return view

    def record_export(
        self,
        workspace_id: str,
        campaign_id: str,
        *,
        export_id: str | None = None,
        object_key: str,
        file_count: int,
        sha256: str,
        manifest: Mapping[str, object],
    ) -> CampaignExportView:
        """Persist one export record (the id may be minted by the caller)."""

        with SessionLocal() as db:
            row = CampaignExport(
                id=export_id or str(uuid4()),
                workspace_id=workspace_id,
                campaign_id=campaign_id,
                object_key=object_key,
                file_count=file_count,
                sha256=sha256,
                manifest_json=dumps_payload(dict(manifest)),
                created_at=utcnow(),
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            view = _export_view(row)
            db.expunge(row)
            return view

    # ------------------------------------------------------------------- read

    def get_campaign(self, workspace_id: str, campaign_id: str) -> CampaignView | None:
        """One campaign, or None (foreign ids read as missing)."""

        with SessionLocal() as db:
            row = db.scalar(
                select(Campaign).where(
                    Campaign.workspace_id == workspace_id,
                    Campaign.id == campaign_id,
                )
            )
            if row is None:
                return None
            view = _campaign_view(row)
            db.expunge(row)
            return view

    def list_campaigns(self, workspace_id: str) -> list[CampaignView]:
        """The workspace's campaigns, newest first."""

        with SessionLocal() as db:
            query = (
                select(Campaign)
                .where(Campaign.workspace_id == workspace_id)
                .order_by(Campaign.created_at.desc(), Campaign.id)
            )
            rows = list(db.scalars(query))
            views = [_campaign_view(row) for row in rows]
            for row in rows:
                db.expunge(row)
            return views

    def get_brief(self, workspace_id: str, campaign_id: str) -> CampaignBriefView | None:
        """The campaign's frozen brief."""

        with SessionLocal() as db:
            row = db.scalar(
                select(CampaignBrief).where(
                    CampaignBrief.workspace_id == workspace_id,
                    CampaignBrief.campaign_id == campaign_id,
                )
            )
            if row is None:
                return None
            view = _brief_view(row)
            db.expunge(row)
            return view

    def list_assets(self, workspace_id: str, campaign_id: str) -> list[CampaignAssetView]:
        """The campaign's deliverables, in timeline then plan order."""

        with SessionLocal() as db:
            query = (
                select(CampaignAsset)
                .where(
                    CampaignAsset.workspace_id == workspace_id,
                    CampaignAsset.campaign_id == campaign_id,
                )
                .order_by(CampaignAsset.day, CampaignAsset.position, CampaignAsset.id)
            )
            rows = list(db.scalars(query))
            views = [_asset_view(row) for row in rows]
            for row in rows:
                db.expunge(row)
            return views

    def get_asset(
        self, workspace_id: str, campaign_id: str, asset_id: str
    ) -> CampaignAssetView | None:
        """One deliverable of one campaign."""

        with SessionLocal() as db:
            row = db.scalar(
                select(CampaignAsset).where(
                    CampaignAsset.workspace_id == workspace_id,
                    CampaignAsset.campaign_id == campaign_id,
                    CampaignAsset.id == asset_id,
                )
            )
            if row is None:
                return None
            view = _asset_view(row)
            db.expunge(row)
            return view

    def list_episodes(self, workspace_id: str, campaign_id: str) -> list[CampaignEpisodeView]:
        """The timeline, Dia 1..Dia 5."""

        with SessionLocal() as db:
            query = (
                select(CampaignEpisode)
                .where(
                    CampaignEpisode.workspace_id == workspace_id,
                    CampaignEpisode.campaign_id == campaign_id,
                )
                .order_by(CampaignEpisode.day, CampaignEpisode.id)
            )
            rows = list(db.scalars(query))
            views = [_episode_view(row) for row in rows]
            for row in rows:
                db.expunge(row)
            return views

    def list_exports(self, workspace_id: str, campaign_id: str) -> list[CampaignExportView]:
        """The campaign's exports, newest first."""

        with SessionLocal() as db:
            query = (
                select(CampaignExport)
                .where(
                    CampaignExport.workspace_id == workspace_id,
                    CampaignExport.campaign_id == campaign_id,
                )
                .order_by(CampaignExport.created_at.desc(), CampaignExport.id)
            )
            rows = list(db.scalars(query))
            views = [_export_view(row) for row in rows]
            for row in rows:
                db.expunge(row)
            return views

    # ------------------------------------------------------------- row builders

    def _campaign_row(self, workspace_id: str, campaign: Mapping[str, object]) -> Campaign:
        now = utcnow()
        return Campaign(
            workspace_id=workspace_id,
            name=clean_text(campaign.get("name"), "name", max_length=160),
            product=clean_text(campaign.get("product"), "product", max_length=160),
            product_type=clean_text(campaign.get("product_type", ""), "product_type", max_length=80),
            audience=clean_text(campaign.get("audience", ""), "audience", max_length=160),
            platform=clean_text(campaign.get("platform", ""), "platform", max_length=80),
            objective=clean_text(campaign.get("objective", ""), "objective", max_length=40),
            status=clean_text(campaign.get("status", "active"), "status", max_length=32),
            seed=self._int_field(campaign.get("seed", 0), "seed"),
            primary_cta=clean_text(campaign.get("primary_cta", ""), "primary_cta", max_length=200),
            created_at=now,
            updated_at=now,
        )

    def _brief_row(self, workspace_id: str, campaign_id: str, brief: Mapping[str, object]) -> CampaignBrief:
        return CampaignBrief(
            workspace_id=workspace_id,
            campaign_id=campaign_id,
            raw_text=clean_text(brief.get("raw_text"), "raw_text", max_length=2000),
            product=clean_text(brief.get("product", ""), "product", max_length=160),
            product_type=clean_text(brief.get("product_type", ""), "product_type", max_length=80),
            audience=clean_text(brief.get("audience", ""), "audience", max_length=160),
            platform=clean_text(brief.get("platform", ""), "platform", max_length=80),
            objective=clean_text(brief.get("objective", ""), "objective", max_length=40),
            duration_seconds=self._int_field(
                brief.get("duration_seconds", 15), "duration_seconds"
            ),
            cta=clean_text(brief.get("cta", ""), "cta", max_length=200),
            missing_json=dumps_array(self._str_list(brief.get("missing", ()))),
            matched_json=dumps_array(self._str_list(brief.get("matched", ()))),
            created_at=utcnow(),
        )

    def _asset_row(self, workspace_id: str, campaign_id: str, asset: Mapping[str, object]) -> CampaignAsset:
        now = utcnow()
        duration = asset.get("duration_seconds")
        return CampaignAsset(
            workspace_id=workspace_id,
            campaign_id=campaign_id,
            day=self._int_field(asset.get("day"), "day"),
            kind=clean_text(asset.get("kind"), "kind", max_length=40),
            label=clean_text(asset.get("label", ""), "label", max_length=120),
            medium=clean_text(asset.get("medium", "image"), "medium", max_length=16),
            aspect_ratio=clean_text(asset.get("aspect_ratio", "1:1"), "aspect_ratio", max_length=16),
            width=self._int_field(asset.get("width", 1080), "width"),
            height=self._int_field(asset.get("height", 1080), "height"),
            duration_seconds=self._int_field(duration, "duration_seconds") if duration is not None else None,
            prompt=clean_text(asset.get("prompt", ""), "prompt", max_length=4000),
            cta=clean_text(asset.get("cta", ""), "cta", max_length=200),
            status=clean_text(asset.get("status", "planned"), "status", max_length=24),
            output_key=self._optional_key(asset.get("output_key"), "output_key"),
            thumbnail_key=self._optional_key(asset.get("thumbnail_key"), "thumbnail_key"),
            position=self._int_field(asset.get("position", 0), "position"),
            created_at=now,
            updated_at=now,
        )

    def _episode_row(self, workspace_id: str, campaign_id: str, episode: Mapping[str, object]) -> CampaignEpisode:
        return CampaignEpisode(
            workspace_id=workspace_id,
            campaign_id=campaign_id,
            day=self._int_field(episode.get("day"), "day"),
            focus=clean_text(episode.get("focus", ""), "focus", max_length=120),
            cta=clean_text(episode.get("cta", ""), "cta", max_length=200),
            notes=clean_text(episode.get("notes", ""), "notes", max_length=2000),
            payload_json=dumps_payload({"asset_kinds": self._str_list(episode.get("asset_kinds", ()))}),
            created_at=utcnow(),
        )

    # ------------------------------------------------------------- normalizers

    @staticmethod
    def _int_field(value: object, field_name: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise CampaignValidationError(f"{field_name} must be an int")
        return value

    @staticmethod
    def _optional_key(value: object, field_name: str) -> str | None:
        if value is None:
            return None
        cleaned = clean_text(value, field_name, max_length=500)
        return cleaned or None

    @staticmethod
    def _str_list(value: object) -> list[str]:
        if isinstance(value, str):
            return [value]
        if not isinstance(value, (list, tuple, set)):
            raise CampaignValidationError("field list must be a sequence of strings")
        return [str(item) for item in value]


#: Module-level singleton for the API layer (same pattern as ``continuity_repo``).
campaign_repo = CampaignRepository()
