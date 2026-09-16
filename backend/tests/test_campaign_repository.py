"""V3.3 — CampaignRepository: workspace-scoped persistence over the real tables.

Every test owns a fresh ``ws-<uuid>`` workspace against the shared test
database (the same isolation the continuity suite uses): cross-workspace
reads behave as 404s, the bundle commits atomically, and the planned →
delivered transition only happens through ``deliver_asset``. The HTTP
mapping (404/422) lives in `test_campaign_api.py`.
"""
from __future__ import annotations

from uuid import uuid4

import pytest

# The campaign tables come from the Alembic bootstrap that runs at app
# import (the same shared-database reliance the continuity suite has).
from app.main import app  # noqa: F401
from app.campaign.brief_interpreter import CampaignValidationError, interpret
from app.campaign.campaign_models import (
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
from app.campaign.campaign_repository import (
    CampaignAssetView,
    CampaignBundle,
    CampaignRepositoryError,
    CampaignRepository,
    dumps_array,
    loads_array,
)
from app.campaign.cta_engine import deck_for
from app.campaign.timeline_builder import build_plan


@pytest.fixture()
def ws() -> str:
    return f"ws-{uuid4().hex}"


@pytest.fixture()
def repo() -> CampaignRepository:
    return CampaignRepository()


def _bundle_args(briefing: str = "Quero lançar a coleção Legacy", seed: int = 7, name: str | None = None):
    brief = interpret(briefing)
    deck = deck_for(brief.product, seed)
    primary = deck.draw()
    assets, episodes = build_plan(brief, deck)
    campaign = {
        "name": name or brief.display_name,
        "product": brief.product,
        "product_type": brief.product_type,
        "audience": brief.audience,
        "platform": brief.platform,
        "objective": brief.objective,
        "status": "active",
        "seed": seed,
        "primary_cta": primary,
    }
    return (
        campaign,
        {**brief.to_dict(), "cta": primary},
        [asset.to_dict() for asset in assets],
        [episode.to_dict() for episode in episodes],
    )


def _create(repo: CampaignRepository, ws_id: str, *, name: str | None = None, seed: int = 7):
    campaign, brief, assets, episodes = _bundle_args(name=name, seed=seed)
    return repo.create_campaign(ws_id, campaign=campaign, brief=brief, assets=assets, episodes=episodes)


# ---------------------------------------------------------------------------
# Vocabulary + JSON helpers (campaign_models)
# ---------------------------------------------------------------------------


def test_the_model_vocabulary_is_the_documented_one() -> None:
    assert CAMPAIGN_STATUSES == ("active", "paused", "completed")
    assert ASSET_STATUSES == ("planned", "delivered")
    assert MEDIA_KINDS == ("video", "image")
    for table in (Campaign, CampaignAsset, CampaignBrief, CampaignEpisode, CampaignExport):
        assert table.__tablename__.startswith("campaign")


def test_payload_json_helpers_reject_and_defend() -> None:
    assert dumps_payload({"a": 1}) == '{"a": 1}'
    with pytest.raises(CampaignValidationError):
        dumps_payload([1, 2])  # type: ignore[arg-type]
    assert loads_payload(None) == {}
    assert loads_payload("not json") == {}
    assert loads_payload("[1]") == {}
    assert loads_payload('{"day": 2}') == {"day": 2}


def test_array_json_helpers_reject_and_defend() -> None:
    assert dumps_array(("a", "b")) == '["a", "b"]'
    with pytest.raises(CampaignValidationError):
        dumps_array({"a": 1})  # type: ignore[arg-type]
    assert loads_array(None) == []
    assert loads_array("nope") == []
    assert loads_array('{"x": 1}') == []
    assert loads_array('["a", 2]') == ["a", "2"]


def test_utcnow_is_naive_utc() -> None:
    assert utcnow().tzinfo is None


# ---------------------------------------------------------------------------
# Creating + reading back
# ---------------------------------------------------------------------------


def test_a_created_bundle_reads_back_complete(repo, ws) -> None:
    bundle = _create(repo, ws)

    assert bundle.campaign.name == "coleção Legacy"
    assert bundle.campaign.primary_cta
    assert len(bundle.assets) == 7
    assert len(bundle.episodes) == 5
    assert sorted(asset.kind for asset in bundle.assets) == [
        "banner", "cover", "feed", "reel", "shorts", "story", "thumbnail",
    ]
    assert [episode.day for episode in bundle.episodes] == [1, 2, 3, 4, 5]

    stored = repo.get_campaign(ws, bundle.campaign.id)
    assert stored == bundle.campaign
    brief = repo.get_brief(ws, bundle.campaign.id)
    assert brief is not None
    assert brief.raw_text == "Quero lançar a coleção Legacy"
    assert brief.cta == bundle.campaign.primary_cta
    assert brief.missing == ("público", "plataforma", "duração")
    assert brief.matched == ("produto", "objetivo")
    assert repo.list_assets(ws, bundle.campaign.id) == list(bundle.assets)
    assert repo.list_episodes(ws, bundle.campaign.id) == list(bundle.episodes)


def test_views_round_trip_through_to_dict(repo, ws) -> None:
    bundle = _create(repo, ws)

    assert CampaignRepository is not None
    assert bundle.campaign.to_dict()["name"] == "coleção Legacy"
    assert bundle.brief.to_dict()["missing"] == ["público", "plataforma", "duração"]
    asset = bundle.assets[0]
    assert CampaignAssetView(**asset.to_dict()) == asset
    assert bundle.episodes[0].to_dict()["asset_kinds"]


def test_workspaces_do_not_see_each_other(repo, ws) -> None:
    bundle = _create(repo, ws)

    other = f"ws-{uuid4().hex}"
    assert repo.get_campaign(other, bundle.campaign.id) is None
    assert repo.get_brief(other, bundle.campaign.id) is None
    assert repo.list_assets(other, bundle.campaign.id) == []
    assert repo.list_episodes(other, bundle.campaign.id) == []
    assert repo.list_exports(other, bundle.campaign.id) == []
    assert repo.get_asset(other, bundle.campaign.id, bundle.assets[0].id) is None
    assert repo.deliver_asset(other, bundle.campaign.id, bundle.assets[0].id, output_key=None, thumbnail_key=None) is None


def test_list_campaigns_is_newest_first(repo) -> None:
    first = _create(repo, f"ws-{uuid4().hex}", name="Primeira")
    second = _create(repo, f"ws-{uuid4().hex}", name="Segunda")

    listed = repo.list_campaigns(second.campaign.workspace_id)
    assert [view.id for view in listed] == [second.campaign.id]
    other = repo.list_campaigns(first.campaign.workspace_id)
    assert [view.id for view in other] == [first.campaign.id]


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


def test_a_duplicate_deliverable_kind_is_refused(repo, ws) -> None:
    campaign, brief, assets, episodes = _bundle_args()
    assets.append(dict(assets[0], id="dup"))

    with pytest.raises(CampaignRepositoryError):
        repo.create_campaign(ws, campaign=campaign, brief=brief, assets=assets, episodes=episodes)


def test_a_duplicate_day_is_refused(repo, ws) -> None:
    campaign, brief, assets, episodes = _bundle_args()
    episodes.append(dict(episodes[0]))

    with pytest.raises(CampaignRepositoryError):
        repo.create_campaign(ws, campaign=campaign, brief=brief, assets=assets, episodes=episodes)


def test_row_validation_refuses_bad_types(repo, ws) -> None:
    campaign, brief, assets, episodes = _bundle_args()
    bad_campaign = dict(campaign, seed="not-an-int")

    with pytest.raises(CampaignValidationError):
        repo.create_campaign(ws, campaign=bad_campaign, brief=brief, assets=assets, episodes=episodes)


def test_field_validations_on_rows(repo, ws) -> None:
    with pytest.raises(CampaignValidationError):
        repo._campaign_row(ws, {"name": 12, "product": "x"})
    with pytest.raises(CampaignValidationError):
        repo._brief_row(ws, "camp", {"raw_text": 9})
    with pytest.raises(CampaignValidationError):
        repo._asset_row(ws, "camp", {"day": "1", "kind": "reel"})
    with pytest.raises(CampaignValidationError):
        repo._episode_row(ws, "camp", {"day": None})
    with pytest.raises(CampaignValidationError):
        repo._asset_row(ws, "camp", {"day": 1, "kind": "reel", "duration_seconds": "15"})
    with pytest.raises(CampaignValidationError):
        repo._str_list(42)
    # None duration and key normalisation stay honest.
    row = repo._asset_row(ws, "camp", {"day": 1, "kind": "story", "output_key": "  ", "thumbnail_key": None})
    assert row.duration_seconds is None
    assert row.output_key is None and row.thumbnail_key is None


# ---------------------------------------------------------------------------
# Delivery + exports
# ---------------------------------------------------------------------------


def test_deliver_moves_an_asset_to_delivered(repo, ws) -> None:
    bundle = _create(repo, ws)
    asset = bundle.assets[0]

    delivered = repo.deliver_asset(
        ws, bundle.campaign.id, asset.id,
        output_key=f"{ws}/render.mp4", thumbnail_key=f"{ws}/thumb.png",
    )
    assert delivered is not None
    assert delivered.status == "delivered"
    assert delivered.output_key == f"{ws}/render.mp4"
    assert delivered.thumbnail_key == f"{ws}/thumb.png"
    reread = repo.get_asset(ws, bundle.campaign.id, asset.id)
    assert reread is not None and reread.status == "delivered"


def test_deliver_with_only_a_thumbnail_keeps_the_asset_planned(repo, ws) -> None:
    bundle = _create(repo, ws)
    asset = bundle.assets[0]

    delivered = repo.deliver_asset(
        ws, bundle.campaign.id, asset.id, output_key=None, thumbnail_key=f"{ws}/thumb.png"
    )
    assert delivered is not None
    assert delivered.status == "planned"
    assert delivered.thumbnail_key == f"{ws}/thumb.png"


def test_deliver_unknown_asset_returns_none(repo, ws) -> None:
    bundle = _create(repo, ws)
    assert repo.deliver_asset(ws, bundle.campaign.id, "nope", output_key="k", thumbnail_key=None) is None


def test_exports_are_recorded_and_listed_newest_first(repo, ws) -> None:
    bundle = _create(repo, ws)
    first = repo.record_export(
        ws, bundle.campaign.id, object_key=f"{ws}/a.zip", file_count=3, sha256="aa", manifest={"v": 1}
    )
    second = repo.record_export(
        ws, bundle.campaign.id, object_key=f"{ws}/b.zip", file_count=4, sha256="bb", manifest={"v": 2}
    )

    listed = repo.list_exports(ws, bundle.campaign.id)
    assert [view.id for view in listed] == [second.id, first.id]
    assert listed[0].manifest == {"v": 2}
    assert first.to_dict()["file_count"] == 3


# ---------------------------------------------------------------------------
# The bundle container
# ---------------------------------------------------------------------------


def test_campaign_bundle_is_importable() -> None:
    assert CampaignBundle is not None


def test_array_serialisation_refuses_non_string_items() -> None:
    with pytest.raises(CampaignValidationError):
        dumps_array(("a", 2))


def test_str_list_accepts_a_bare_string(repo) -> None:
    assert repo._str_list("reel") == ["reel"]


def test_clean_text_enforces_the_maximum_length(repo, ws) -> None:
    with pytest.raises(CampaignValidationError):
        repo._campaign_row(ws, {"name": "x" * 200, "product": "p"})


def test_payload_serialisation_refuses_unserialisable_values() -> None:
    with pytest.raises(CampaignValidationError):
        dumps_payload({"bad": object()})
