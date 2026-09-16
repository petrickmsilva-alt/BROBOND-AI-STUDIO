"""V3.3 — Timeline Builder: seven deliverables, five days, zero new prompts.

Pins the deliverable catalogue (Reel 9:16, Story, Shorts, Banner,
Thumbnail, Feed 1:1, YouTube Cover — each with its format and medium), the
five-day plan (each day with a *different* set of assets), the composed
prompts and the invariants that keep the plan and the catalogue welded
together.
"""
from __future__ import annotations

import pytest

from app.campaign.brief_interpreter import interpret
from app.campaign.cta_engine import deck_for
from app.campaign.timeline_builder import (
    DAY_PLAN,
    DELIVERABLES,
    DELIVERABLES_BY_KIND,
    SCENE_HINTS,
    TOTAL_DAYS,
    AssetPlan,
    DayFocus,
    DeliverableSpec,
    EpisodePlan,
    build_plan,
    compose_prompt,
)


def _brief(text: str = "Quero lançar a coleção Legacy para o público premium no instagram, vídeos de 15s"):
    return interpret(text)


@pytest.fixture()
def deck():
    return deck_for("Legacy", 42)


# ---------------------------------------------------------------------------
# The catalogue
# ---------------------------------------------------------------------------


def test_the_seven_sprint_deliverables_exist() -> None:
    assert {spec.kind for spec in DELIVERABLES} == {
        "reel", "story", "shorts", "banner", "thumbnail", "feed", "cover",
    }


def test_each_deliverable_has_its_format() -> None:
    by_kind = DELIVERABLES_BY_KIND
    assert by_kind["reel"].label == "Reel 9:16"
    assert by_kind["reel"].medium == "video"
    assert (by_kind["reel"].width, by_kind["reel"].height) == (1080, 1920)
    assert by_kind["story"].aspect_ratio == "9:16"
    assert by_kind["shorts"].medium == "video"
    assert by_kind["banner"].aspect_ratio == "1.91:1"
    assert (by_kind["banner"].width, by_kind["banner"].height) == (1200, 628)
    assert by_kind["thumbnail"].aspect_ratio == "16:9"
    assert by_kind["feed"].aspect_ratio == "1:1"
    assert (by_kind["feed"].width, by_kind["feed"].height) == (1080, 1080)
    assert (by_kind["cover"].width, by_kind["cover"].height) == (2560, 1440)
    # Images are stills: no duration claim, videos carry one.
    for spec in DELIVERABLES:
        if spec.medium == "image":
            assert spec.duration_seconds is None
        else:
            assert spec.duration_seconds is not None


def test_every_scene_hint_covers_a_deliverable() -> None:
    assert set(SCENE_HINTS) == set(DELIVERABLES_BY_KIND)
    for kind, hint in SCENE_HINTS.items():
        assert "{product}" in hint, kind


def test_deliverable_spec_round_trips() -> None:
    spec = DELIVERABLES_BY_KIND["reel"]
    assert DeliverableSpec(**spec.to_dict()) == spec


# ---------------------------------------------------------------------------
# The five-day plan
# ---------------------------------------------------------------------------


def test_the_timeline_is_five_days() -> None:
    assert [day.day for day in DAY_PLAN] == list(range(1, TOTAL_DAYS + 1))
    assert TOTAL_DAYS == 5


def test_every_deliverable_is_scheduled_exactly_once() -> None:
    scheduled = [kind for day in DAY_PLAN for kind in day.kinds]
    assert sorted(scheduled) == sorted(DELIVERABLES_BY_KIND)
    assert len(scheduled) == len(set(scheduled))


def test_each_day_runs_a_different_set_of_assets() -> None:
    sets = [frozenset(day.kinds) for day in DAY_PLAN]
    assert len(set(sets)) == len(sets), "two days running the same assets is not a campaign arc"


def test_day_focus_is_frozen_data() -> None:
    day = DAY_PLAN[0]
    assert DayFocus(**day.__dict__) == day


# ---------------------------------------------------------------------------
# build_plan
# ---------------------------------------------------------------------------


def test_the_plan_carries_seven_assets_and_five_days(deck) -> None:
    assets, episodes = build_plan(_brief(), deck)

    assert len(assets) == 7
    assert len(episodes) == 5
    assert sorted(asset.kind for asset in assets) == sorted(DELIVERABLES_BY_KIND)
    assert [episode.day for episode in episodes] == [1, 2, 3, 4, 5]


def test_assets_land_on_their_scheduled_days(deck) -> None:
    assets, _ = build_plan(_brief(), deck)

    for day in DAY_PLAN:
        on_day = [asset for asset in assets if asset.day == day.day]
        assert sorted(asset.kind for asset in on_day) == sorted(day.kinds)


def test_the_plan_never_repeats_a_cta(deck) -> None:
    assets, episodes = build_plan(_brief(), deck)

    drawn = [asset.cta for asset in assets] + [episode.cta for episode in episodes]
    assert len(drawn) == 12
    assert len({cta.casefold() for cta in drawn}) == 12


def test_video_assets_carry_the_brief_duration_and_images_do_not(deck) -> None:
    assets, _ = build_plan(_brief(), deck)

    for asset in assets:
        if asset.medium == "video":
            assert asset.duration_seconds == 15
        else:
            assert asset.duration_seconds is None


def test_the_prompt_is_composed_from_the_brief(deck) -> None:
    assets, _ = build_plan(_brief(), deck)

    reel = next(asset for asset in assets if asset.kind == "reel")
    assert "Legacy" in reel.prompt
    assert "público premium" in reel.prompt
    assert "instagram" in reel.prompt
    assert "15-second cut" in reel.prompt
    assert reel.cta in reel.prompt
    story = next(asset for asset in assets if asset.kind == "story")
    assert "cut" not in story.prompt, "a still has no duration"


def test_the_enhancer_is_applied_when_passed(deck) -> None:
    calls: list[str] = []

    def enhance(prompt: str, *, style: str = "") -> str:
        calls.append(prompt)
        return f"ENHANCED[{style}]: {prompt}"

    assets, _ = build_plan(_brief(), deck, enhance=enhance)
    assert len(calls) == 7
    assert all(asset.prompt.startswith("ENHANCED[cinematic realism]:") for asset in assets)


def test_without_an_enhancer_the_composed_prompt_is_used_as_is(deck) -> None:
    assets, _ = build_plan(_brief(), deck)
    reel = next(asset for asset in assets if asset.kind == "reel")
    base = compose_prompt(DELIVERABLES_BY_KIND["reel"], _brief(), reel.cta, "Lançamento")
    assert reel.prompt == base


def test_compose_prompt_uses_the_fallback_product_when_unread() -> None:
    brief = interpret("quero vender muito")
    prompt = compose_prompt(DELIVERABLES_BY_KIND["feed"], brief, "CTA.", "Conversão")
    assert "Nova coleção" in prompt


def test_plan_views_round_trip(deck) -> None:
    assets, episodes = build_plan(_brief(), deck)

    assert AssetPlan(**assets[0].to_dict()) == assets[0]
    first = episodes[0]
    rebuilt = EpisodePlan(**{**first.to_dict(), "asset_kinds": tuple(first.to_dict()["asset_kinds"])})
    assert rebuilt == first


def test_the_plan_refuses_a_drifted_catalogue(deck, monkeypatch) -> None:
    from app.campaign import timeline_builder

    monkeypatch.setattr(
        timeline_builder,
        "DAY_PLAN",
        (
            DayFocus(1, "Lançamento", ("reel",)),
            DayFocus(2, "Bastidores", ("story",)),
            DayFocus(3, "Alcance", ("shorts",)),
            DayFocus(4, "Conversão", ("feed",)),
            DayFocus(5, "Última chamada", ("banner",)),
        ),
    )
    with pytest.raises(Exception):
        build_plan(_brief(), deck)


def test_the_plan_refuses_a_duplicated_schedule(deck, monkeypatch) -> None:
    from app.campaign import timeline_builder

    monkeypatch.setattr(
        timeline_builder,
        "DAY_PLAN",
        (
            DayFocus(1, "Lançamento", ("reel", "story")),
            DayFocus(2, "Bastidores", ("reel", "story")),
            DayFocus(3, "Alcance", ("shorts",)),
            DayFocus(4, "Conversão", ("feed",)),
            DayFocus(5, "Última chamada", ("banner",)),
        ),
    )
    with pytest.raises(Exception):
        build_plan(_brief(), deck)


def test_the_plan_refuses_a_timeline_out_of_order(deck, monkeypatch) -> None:
    from app.campaign import timeline_builder

    monkeypatch.setattr(
        timeline_builder,
        "DAY_PLAN",
        tuple(reversed(timeline_builder.DAY_PLAN)),
    )
    with pytest.raises(Exception):
        build_plan(_brief(), deck)


def test_the_plan_refuses_an_asset_count_drift(deck, monkeypatch) -> None:
    """A six-day plan that reuses kinds produces 9 assets: refused, not trimmed."""

    from app.campaign import timeline_builder

    monkeypatch.setattr(
        timeline_builder,
        "DAY_PLAN",
        (
            DayFocus(1, "Lançamento", ("reel", "thumbnail")),
            DayFocus(2, "Reprise", ("reel", "thumbnail")),
            DayFocus(3, "Alcance", ("shorts", "cover")),
            DayFocus(4, "Conversão", ("feed",)),
            DayFocus(5, "Bastidores", ("story",)),
            DayFocus(6, "Última chamada", ("banner",)),
        ),
    )
    with pytest.raises(Exception):
        build_plan(_brief(), deck)
