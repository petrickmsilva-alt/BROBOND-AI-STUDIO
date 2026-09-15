"""StyleResolver: the user picks a style, never a prompt."""
import pytest

from app.core.contracts import StylePreset
from app.core.style_resolver import (
    DEFAULT_STYLE_ID,
    NEUTRAL_STYLE_ID,
    SEED_STYLES,
    SeedStyleSource,
    StyleResolver,
)

#: The five styles named in the mission brief.
REQUIRED_STYLES = {"imax-hero", "john-wick", "luxury-fashion", "neo-tokyo", "marvel-trailer"}

#: Every style must carry the full vocabulary from ETAPA 5.
STYLE_ATTRIBUTES = ("lens", "lut", "lighting", "contrast", "grain", "camera_motion", "particles", "fps")


@pytest.fixture()
def styles() -> StyleResolver:
    return StyleResolver()


def test_every_style_named_in_the_mission_exists(styles: StyleResolver) -> None:
    available = {style.style_id for style in styles.catalog()}
    assert REQUIRED_STYLES <= available


def test_every_style_carries_the_full_technical_vocabulary(styles: StyleResolver) -> None:
    for style in styles.catalog():
        for attribute in STYLE_ATTRIBUTES:
            value = getattr(style, attribute)
            assert value not in ("", None), f"{style.style_id} is missing {attribute}"


def test_styles_resolve_by_id_and_by_display_name(styles: StyleResolver) -> None:
    assert styles.resolve("john-wick").name == "JOHN WICK"
    assert styles.resolve("JOHN WICK").style_id == "john-wick"
    assert styles.resolve("Luxury Fashion").style_id == "luxury-fashion"


def test_unknown_style_falls_back_to_neutral_instead_of_borrowing_a_look(styles: StyleResolver) -> None:
    fallback = styles.resolve("a-style-that-does-not-exist")
    assert fallback.style_id == NEUTRAL_STYLE_ID
    assert styles.is_known("a-style-that-does-not-exist") is False


def test_absent_style_uses_the_brobond_default(styles: StyleResolver) -> None:
    assert styles.resolve(None).style_id == DEFAULT_STYLE_ID
    assert styles.resolve("").style_id == DEFAULT_STYLE_ID
    assert styles.resolve_default().style_id == DEFAULT_STYLE_ID


def test_default_style_matches_the_pre_core_prompt_enhancer(styles: StyleResolver) -> None:
    """`PromptEnhancer.default_style` was "cinematic realism" before the Core."""

    assert styles.resolve_default().name.lower() == "cinematic realism"


def test_style_vocabulary_is_described_without_camera_detail(styles: StyleResolver) -> None:
    described = styles.describe(styles.resolve("neo-tokyo"))
    assert "neo tokyo" in described
    assert "cyan" in described


def test_style_exposes_lighting_lens_motion_and_environment(styles: StyleResolver) -> None:
    preset = styles.resolve("imax-hero")
    assert styles.lighting_phrase(preset) == preset.lighting
    assert styles.lens_phrase(preset) == preset.lens
    assert preset.camera_motion in styles.motion_phrase(preset)
    assert styles.environment_phrase(preset) == preset.particles


def test_catalog_is_searchable(styles: StyleResolver) -> None:
    assert {style.style_id for style in styles.catalog("luxury")} >= {"luxury-fashion"}
    assert styles.catalog("") == styles.catalog()


def test_presets_are_immutable(styles: StyleResolver) -> None:
    with pytest.raises(Exception):
        styles.resolve("john-wick").fps = 60  # type: ignore[misc]


def test_a_persistent_source_can_replace_the_seeds() -> None:
    class OneStyle:
        def fetch(self, style_id: str) -> StylePreset | None:
            return None

        def search(self, query: str = "") -> list[StylePreset]:
            return []

    resolver = StyleResolver(source=OneStyle())
    # Even with an empty source the resolver must hand back something usable.
    assert resolver.resolve("anything").style_id == SEED_STYLES[-1].style_id


def test_seed_source_accepts_new_styles_for_etapa_5() -> None:
    source = SeedStyleSource()
    source.register(
        StylePreset(
            style_id="custom",
            name="Custom",
            lens="50mm",
            lut="x",
            lighting="y",
            contrast="z",
            grain="none",
            camera_motion="static",
            particles="none",
            fps=30,
        )
    )
    resolver = StyleResolver(source=source)
    assert resolver.resolve("custom").fps == 30
    assert resolver.resolve("Custom").style_id == "custom"
