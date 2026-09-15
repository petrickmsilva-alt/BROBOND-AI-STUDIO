"""ShotResolver: stable codes resolve into direction presets, never prompt blobs."""
import pytest

from app.core.contracts import ShotPreset
from app.core.shot_resolver import SEED_SHOTS, SeedShotSource, ShotResolver

#: Codes already published in knowledge_base/SHOT_LIBRARY.md and seeded in
#: backend/app/knowledge.py. Shot codes are stable identifiers, so this test
#: pins them: renumbering the library must fail here first.
PUBLISHED_CODES = {"SH001", "SH014", "SH032", "SH051", "SH089", "SH120", "SH121", "SH122", "SH123", "SH124"}

SHOT_ATTRIBUTES = ("camera_path", "speed", "lens", "focus", "shake", "depth")


@pytest.fixture()
def shots() -> ShotResolver:
    return ShotResolver()


def test_every_published_shot_code_is_preserved(shots: ShotResolver) -> None:
    available = {shot.code for shot in shots.catalog()}
    assert PUBLISHED_CODES <= available


def test_the_knowledge_base_seeds_all_resolve(shots: ShotResolver) -> None:
    """knowledge.py seeds SH001, SH014, SH032, SH051 and SH120."""

    for code in ("SH001", "SH014", "SH032", "SH051", "SH120"):
        assert shots.resolve(code) is not None, f"{code} disappeared from the library"


def test_hero_walk_keeps_its_published_direction(shots: ShotResolver) -> None:
    hero = shots.resolve("SH001")
    assert hero.name == "Hero Walk"
    assert hero.lens == "50mm"
    assert "low-angle tracking" in hero.camera_path


def test_every_shot_carries_the_full_preset_vocabulary(shots: ShotResolver) -> None:
    for shot in shots.catalog():
        for attribute in SHOT_ATTRIBUTES:
            assert getattr(shot, attribute), f"{shot.code} is missing {attribute}"


def test_lookup_accepts_code_or_name_and_is_case_insensitive(shots: ShotResolver) -> None:
    assert shots.resolve("sh001").name == "Hero Walk"
    assert shots.resolve("Hero Walk").code == "SH001"
    assert shots.resolve("  drone reveal ").code == "SH032"


def test_unknown_shot_returns_none_rather_than_inventing_camera_language(shots: ShotResolver) -> None:
    assert shots.resolve("SH999") is None
    assert shots.resolve(None) is None
    assert shots.resolve("") is None
    assert shots.is_known("SH999") is False


def test_camera_lens_and_motion_phrases_are_populated(shots: ShotResolver) -> None:
    shot = shots.resolve("SH121")
    assert "shoulder pursuit" in shots.camera_phrase(shot)
    assert "50mm" in shots.lens_phrase(shot)
    assert "handheld" in shots.motion_phrase(shot)


def test_phrases_are_empty_for_a_missing_shot(shots: ShotResolver) -> None:
    assert shots.camera_phrase(None) == ""
    assert shots.lens_phrase(None) == ""
    assert shots.motion_phrase(None) == ""


def test_a_locked_shot_reports_static_motion_without_shake(shots: ShotResolver) -> None:
    """`shake="none"` is dropped; `speed="static"` is meaningful and kept."""

    assert shots.motion_phrase(shots.resolve("SH124")) == "static"
    assert "none" not in shots.motion_phrase(shots.resolve("SH124"))


def test_describe_reads_as_direction_not_as_a_prompt(shots: ShotResolver) -> None:
    line = shots.describe(shots.resolve("SH032"))
    assert line.startswith("SH032 Drone Reveal")
    assert "24mm" in line


def test_catalog_is_searchable_by_intention(shots: ShotResolver) -> None:
    assert any(shot.code == "SH089" for shot in shots.catalog("reflection"))


def test_shot_count_is_reported_for_the_visual_browser(shots: ShotResolver) -> None:
    assert shots.count() == len(SEED_SHOTS) == 10


def test_presets_are_immutable(shots: ShotResolver) -> None:
    with pytest.raises(Exception):
        shots.resolve("SH001").lens = "12mm"  # type: ignore[misc]


def test_a_persistent_source_can_replace_the_seeds() -> None:
    class EmptyShots:
        def fetch(self, code: str) -> ShotPreset | None:
            return None

        def search(self, query: str = "") -> list[ShotPreset]:
            return []

    resolver = ShotResolver(source=EmptyShots())
    assert resolver.resolve("SH001") is None
    assert resolver.count() == 0


def test_seed_source_accepts_new_shots_for_etapa_6() -> None:
    source = SeedShotSource()
    source.register(
        ShotPreset(
            code="SH300",
            name="New Shot",
            camera_path="static",
            speed="static",
            lens="50mm",
            focus="even",
            shake="none",
            depth="medium",
        )
    )
    assert ShotResolver(source=source).resolve("SH300").name == "New Shot"
