"""V3.3 — Campaign Service: briefing in, complete campaign out.

The composition root of the Campaign Builder. One call —
``create_from_briefing`` — runs the whole sprint flow:

1. the **Brief Interpreter** reads the raw text into a ``InterpretedBrief``;
2. the **CTA Engine** mints a seeded, never-repeating deck and draws the
   primary CTA plus one per deliverable and one per day;
3. the **Timeline Builder** schedules the seven deliverables across
   Dia 1..Dia 5 and composes each generation prompt (expanded through the
   existing ``PromptEnhancer`` — the Core's ``PromptCompiler`` facade);
4. the repository persists the complete bundle in one transaction.

The service also owns **duplication** (a fresh CTA seed, deliveries reset),
**delivery** (attaching real stored files to planned assets) and the
**Export Center** flow (manifest + ZIP through the storage adapter).

The Provider Registry, the Render Engine and the Director AI are not
altered: the builder plans and packages, it never renders — an asset only
becomes ``delivered`` when a real stored file is attached to it.
"""
from __future__ import annotations

import secrets
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from uuid import uuid4

from . import export_center
from .brief_interpreter import (
    CampaignValidationError,
    InterpretedBrief,
    interpret,
)
from .campaign_repository import (
    CampaignAssetView,
    CampaignBundle,
    CampaignBriefView,
    CampaignEpisodeView,
    CampaignExportView,
    CampaignRepository,
    CampaignView,
    campaign_repo,
)
from .cta_engine import CTADeck, deck_for
from .timeline_builder import DELIVERABLES, build_plan


class CampaignError(Exception):
    """Base class for service-level failures the routes map to HTTP."""


class UnknownCampaignError(CampaignError):
    """The campaign id does not exist in the caller's workspace (404)."""


class UnknownAssetError(CampaignError):
    """The asset id does not exist in the campaign (404)."""


class InvalidDeliveryError(CampaignError):
    """The attached object key is not a real file of this workspace (422)."""


@dataclass(frozen=True)
class CampaignDetail:
    """A campaign plus everything it owns."""

    campaign: CampaignView
    brief: CampaignBriefView
    assets: tuple[CampaignAssetView, ...]
    episodes: tuple[CampaignEpisodeView, ...]
    exports: tuple[CampaignExportView, ...]


class CampaignService:
    """The builder's orchestrator — the only module that imports the others."""

    def __init__(
        self,
        repository: CampaignRepository | None = None,
        storage_adapter=None,
        prompt_enhancer: Callable[..., str] | None = None,
        seed_factory: Callable[[], int] | None = None,
    ) -> None:
        self._repository = repository or campaign_repo
        self._storage = storage_adapter
        self._enhancer = prompt_enhancer
        self._seed_factory = seed_factory

    # ------------------------------------------------------------- adapters

    @property
    def storage(self):
        """The storage adapter, resolved lazily so tests can inject a fake."""

        if self._storage is None:
            from ..storage import storage as default_storage

            self._storage = default_storage
        return self._storage

    def _enhance(self, prompt: str, *, style: str = "cinematic realism") -> str:
        """Expand a composed prompt through the existing prompt engine."""

        if self._enhancer is None:
            from ..prompt_engine import PromptEnhancer

            self._enhancer = PromptEnhancer().enhance
        return self._enhancer(prompt, style=style)

    def _seed(self) -> int:
        factory = self._seed_factory or (lambda: secrets.randbits(32))
        return factory()

    # -------------------------------------------------------------- reading

    @staticmethod
    def interpret(raw_text: str) -> InterpretedBrief:
        """The Brief Interpreter, without persisting anything."""

        return interpret(raw_text)

    def list_campaigns(self, workspace_id: str) -> list[CampaignView]:
        return self._repository.list_campaigns(workspace_id)

    def get_detail(self, workspace_id: str, campaign_id: str) -> CampaignDetail:
        """One campaign with brief, assets, timeline and exports."""

        campaign = self._repository.get_campaign(workspace_id, campaign_id)
        if campaign is None:
            raise UnknownCampaignError(f"campaign {campaign_id} not found")
        brief = self._repository.get_brief(workspace_id, campaign_id)
        assets = tuple(self._repository.list_assets(workspace_id, campaign_id))
        episodes = tuple(self._repository.list_episodes(workspace_id, campaign_id))
        exports = tuple(self._repository.list_exports(workspace_id, campaign_id))
        return CampaignDetail(
            campaign=campaign,
            brief=brief,
            assets=assets,
            episodes=episodes,
            exports=exports,
        )

    # -------------------------------------------------------------- building

    def create_from_briefing(
        self, workspace_id: str, raw_text: str, *, name: str | None = None
    ) -> CampaignBundle:
        """The whole sprint in one call: brief → deliverables → timeline."""

        brief = self.interpret(raw_text)
        return self._build_bundle(workspace_id, brief, name=name)

    def duplicate(
        self, workspace_id: str, campaign_id: str, *, name: str | None = None
    ) -> CampaignBundle:
        """Copy a campaign: same brief fields, freshly armed CTAs and plan.

        The copy starts clean — every asset back to ``planned``, delivered
        files not inherited — and a new seed re-shuffles the CTA deck, so
        the duplicate never repeats its origin's CTA assignments.
        """

        original = self.get_detail(workspace_id, campaign_id)
        stored = original.brief
        brief = InterpretedBrief(
            raw_text=stored.raw_text,
            product=stored.product,
            product_type=stored.product_type,
            audience=stored.audience,
            platform=stored.platform,
            objective=stored.objective,
            duration_seconds=stored.duration_seconds,
            missing=stored.missing,
            matched=stored.matched,
        )
        copy_name = (name or "").strip() or f"{original.campaign.name} (cópia)"
        return self._build_bundle(workspace_id, brief, name=copy_name)

    def _build_bundle(
        self, workspace_id: str, brief: InterpretedBrief, *, name: str | None
    ) -> CampaignBundle:
        seed = self._seed()
        deck = deck_for(brief.product, seed)
        primary_cta = deck.draw()
        assets, episodes = build_plan(brief, deck, enhance=self._enhance)
        campaign_name = (name or "").strip() or brief.display_name
        return self._repository.create_campaign(
            workspace_id,
            campaign={
                "name": campaign_name,
                "product": brief.product,
                "product_type": brief.product_type,
                "audience": brief.audience,
                "platform": brief.platform,
                "objective": brief.objective,
                "status": "active",
                "seed": seed,
                "primary_cta": primary_cta,
            },
            brief={
                **brief.to_dict(),
                "cta": primary_cta,
            },
            assets=[asset.to_dict() for asset in assets],
            episodes=[episode.to_dict() for episode in episodes],
        )

    # ------------------------------------------------------------- delivering

    def deliver(
        self,
        workspace_id: str,
        campaign_id: str,
        asset_id: str,
        *,
        output_key: str | None = None,
        thumbnail_key: str | None = None,
    ) -> CampaignAssetView:
        """Attach real stored files to a planned asset (planned → delivered).

        Keys must live inside the caller's workspace and exist in storage —
        the campaign never claims a file that is not there.
        """

        if not output_key and not thumbnail_key:
            raise InvalidDeliveryError("inform output_key and/or thumbnail_key to deliver")
        asset = self._repository.get_asset(workspace_id, campaign_id, asset_id)
        if asset is None:
            campaign = self._repository.get_campaign(workspace_id, campaign_id)
            if campaign is None:
                raise UnknownCampaignError(f"campaign {campaign_id} not found")
            raise UnknownAssetError(f"asset {asset_id} not found")
        for key in (output_key, thumbnail_key):
            if not key:
                continue
            cleaned = key.strip()
            if not cleaned.startswith(f"{workspace_id}/"):
                raise InvalidDeliveryError("object key must belong to the caller's workspace")
            if not self.storage.exists(cleaned):
                raise InvalidDeliveryError(f"object {cleaned} does not exist in storage")
        delivered = self._repository.deliver_asset(
            workspace_id,
            campaign_id,
            asset_id,
            output_key=output_key,
            thumbnail_key=thumbnail_key,
        )
        assert delivered is not None  # the existence check above ran first
        return delivered

    # -------------------------------------------------------------- exporting

    def export(self, workspace_id: str, campaign_id: str) -> CampaignExportView:
        """Build the Export Center ZIP and record the export."""

        detail = self.get_detail(workspace_id, campaign_id)
        manifest = export_center.build_manifest(
            detail.campaign.to_dict(),
            detail.brief.to_dict() if detail.brief else {},
            [asset.to_dict() for asset in detail.assets],
            [episode.to_dict() for episode in detail.episodes],
        )
        binaries = self._collect_binaries(workspace_id, detail.assets)
        package = export_center.build_zip(manifest, [asset.to_dict() for asset in detail.assets], binaries)

        export_id = str(uuid4())
        object_key = f"{workspace_id}/campaigns/{campaign_id}/exports/{export_id}.zip"
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as handle:
            handle.write(package.data)
            source = Path(handle.name)
        try:
            self.storage.upload_path(source, object_key, "application/zip")
        finally:
            source.unlink(missing_ok=True)
        return self._repository.record_export(
            workspace_id,
            campaign_id,
            export_id=export_id,
            object_key=object_key,
            file_count=package.file_count,
            sha256=package.sha256,
            manifest=manifest,
        )

    def _collect_binaries(self, workspace_id: str, assets: tuple[CampaignAssetView, ...]) -> dict[str, bytes]:
        """Read the delivered files into the archive paths — real bytes only."""

        binaries: dict[str, bytes] = {}
        for asset in assets:
            folder = export_center.asset_folder(asset.to_dict())
            for attr, filename in (
                ("output_key", export_center.DELIVERY_FILENAMES.get(asset.medium)),
                ("thumbnail_key", export_center.THUMBNAIL_FILENAME),
            ):
                key = getattr(asset, attr) if filename else None
                if not key or not key.startswith(f"{workspace_id}/") or not self.storage.exists(key):
                    continue
                path = self.storage.download(key, self.storage.local_path(key))
                binaries[f"{folder}/{filename}"] = Path(path).read_bytes()
        return binaries


#: Module-level singleton for the API layer.
campaign_service = CampaignService()

__all__ = [
    "CTADeck",
    "CampaignDetail",
    "CampaignError",
    "CampaignService",
    "DELIVERABLES",
    "InvalidDeliveryError",
    "UnknownAssetError",
    "UnknownCampaignError",
    "campaign_service",
    "deck_for",
]
