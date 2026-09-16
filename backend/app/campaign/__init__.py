"""V3.3 — Campaign Builder.

One briefing in, a complete campaign out: seven deliverables (Reel 9:16,
Story, Shorts, Banner, Thumbnail, Feed 1:1, YouTube Cover), a five-day
timeline with a different focus per day, a CTA deck that never repeats
within a campaign, and an Export Center ZIP (manifest, prompts, metadata
and every delivered MP4/PNG/thumbnail).

Layering (same rule as ``continuity/``): ``brief_interpreter``,
``cta_engine``, ``timeline_builder`` and ``export_center`` are
framework-free and reason over plain data; ``campaign_models`` holds the
SQLAlchemy tables; ``campaign_repository`` is the only module that touches
the database; ``campaign_service`` composes the whole flow at the
application boundary, expanding prompts through the existing
``PromptEnhancer`` (Core's ``PromptCompiler`` facade).

The Director AI, the Provider Registry and the Render Engine are not
altered: the builder plans, schedules and packages. An asset becomes
``delivered`` only when a real stored file is attached to it — the
campaign never claims a render that does not exist.
"""
from .brief_interpreter import (
    AUDIENCES,
    DEFAULT_AUDIENCE,
    DEFAULT_DURATION_SECONDS,
    DEFAULT_OBJECTIVE,
    DEFAULT_PLATFORM,
    DEFAULT_PRODUCT,
    OBJECTIVES,
    PLATFORMS,
    PRODUCT_MARKERS,
    InterpretedBrief,
    CampaignValidationError,
    interpret,
)
from .campaign_models import (
    ASSET_STATUSES,
    CAMPAIGN_STATUSES,
    MEDIA_KINDS,
    Campaign,
    CampaignAsset,
    CampaignBrief,
    CampaignEpisode,
    CampaignExport,
    dumps_payload,
    loads_payload,
    utcnow,
)
from .campaign_repository import (
    CampaignAssetView,
    CampaignBundle,
    CampaignBriefView,
    CampaignEpisodeView,
    CampaignExportView,
    CampaignRepository,
    CampaignRepositoryError,
    CampaignView,
    campaign_repo,
)
from .campaign_service import (
    CampaignDetail,
    CampaignError,
    CampaignService,
    InvalidDeliveryError,
    UnknownAssetError,
    UnknownCampaignError,
    campaign_service,
)
from .cta_engine import (
    CTA_TEMPLATES,
    CTADeck,
    CTAExhaustedError,
    deck_for,
)
from .export_center import (
    MANIFEST_VERSION,
    ExportPackage,
    asset_folder,
    build_manifest,
    build_zip,
    read_manifest,
)
from .timeline_builder import (
    DAY_PLAN,
    DELIVERABLES,
    DELIVERABLES_BY_KIND,
    TOTAL_DAYS,
    AssetPlan,
    DayFocus,
    DeliverableSpec,
    EpisodePlan,
    build_plan,
    compose_prompt,
)

__all__ = [
    "ASSET_STATUSES",
    "AUDIENCES",
    "CAMPAIGN_STATUSES",
    "CTA_TEMPLATES",
    "Campaign",
    "CampaignAsset",
    "CampaignAssetView",
    "CampaignBrief",
    "CampaignBriefView",
    "CampaignBundle",
    "CampaignDetail",
    "CampaignEpisode",
    "CampaignEpisodeView",
    "CampaignError",
    "CampaignExport",
    "CampaignExportView",
    "CampaignRepository",
    "CampaignRepositoryError",
    "CampaignService",
    "CampaignValidationError",
    "CampaignView",
    "CTADeck",
    "CTAExhaustedError",
    "DAY_PLAN",
    "DEFAULT_AUDIENCE",
    "DEFAULT_DURATION_SECONDS",
    "DEFAULT_OBJECTIVE",
    "DEFAULT_PLATFORM",
    "DEFAULT_PRODUCT",
    "DELIVERABLES",
    "DELIVERABLES_BY_KIND",
    "AssetPlan",
    "DayFocus",
    "DeliverableSpec",
    "EpisodePlan",
    "ExportPackage",
    "InterpretedBrief",
    "InvalidDeliveryError",
    "MANIFEST_VERSION",
    "MEDIA_KINDS",
    "OBJECTIVES",
    "PLATFORMS",
    "PRODUCT_MARKERS",
    "TOTAL_DAYS",
    "UnknownAssetError",
    "UnknownCampaignError",
    "asset_folder",
    "build_manifest",
    "build_plan",
    "build_zip",
    "campaign_repo",
    "campaign_service",
    "compose_prompt",
    "deck_for",
    "dumps_payload",
    "interpret",
    "loads_payload",
    "read_manifest",
    "utcnow",
]
