"""ETAPA 5 — CinematicLibrary.

The grammar constants are pinned against knowledge_base/CINEMATIC_BIBLE.md, so
a future edit that invents vocabulary or drops a rule fails here rather than
silently drifting away from the document.
"""
import pytest

from app.core.cinematic_library import (
    ANGLES,
    FRAMES,
    LENSES,
    LIGHTS,
    MOTIVATIONS,
    RULE_GRAIN_CONSISTENT,
    RULE_GRAIN_SUBTLE,
    RULE_HAZE_HAS_PURPOSE,
    RULE_LENS_DECLARED,
    RULE_MOTION_MOTIVATED,
    RULE_PROTECT_HIGHLIGHTS,
    RULE_SKIN_NATURAL,
    RULE_TEAL_AMBER_SPARINGLY,
    STATUS_ATTENTION,
    STATUS_OK,
    STATUS_VIOLATION,
    TIME_QUALITIES,
    CinematicLibrary,
)
from app.core.contracts import ShotPreset, StylePreset
from app.core.shot_resolver import SEED_SHOTS
from app.core.style_resolver import SEED_STYLES


@pytest.fixture()
def lib() -> CinematicLibrary:
    return CinematicLibrary()


def _style(**overrides) -> StylePreset:
    base = dict(
        style_id="test-style",
        name="Test Style",
        lens="85mm",
        lut="neutral filmic",
        lighting="soft key, gentle rim",
        contrast="balanced, natural skin",
        grain="none",
        camera_motion="slow dolly-in",
        particles="none",
        fps=24,
        palette="neutral",
    )
    base.update(overrides)
    return StylePreset(**base)


def _shot(**overrides) -> ShotPreset:
    base = dict(
        code="SH999",
        name="Test Shot",
        camera_path="slow push-in",
        speed="slow",
        lens="50mm",
        focus="subject locked",
        shake="none",
        depth="medium",
    )
    base.update(overrides)
    return ShotPreset(**base)


# ------------------------------------------------- the grammar is the document


def test_the_lens_language_is_the_five_focal_lengths_the_bible_names(lib) -> None:
    """CINEMATIC_BIBLE.md "Lens language" lists exactly 24/35/50/85/135."""

    assert [profile.focal_mm for profile in lib.lenses()] == [24, 35, 50, 85, 135]
    assert len(LENSES) == 5


def test_lens_semantics_are_verbatim_from_the_bible(lib) -> None:
    assert lib.lens(24).semantics == ("scale", "environment", "vulnerability", "architecture")
    assert lib.lens(135).semantics == ("observation", "isolation", "premium editorial detail")
    assert lib.lens(85).semantics == ("portrait", "luxury", "compression", "separation")


def test_an_unknown_focal_length_is_none_not_an_invention(lib) -> None:
    assert lib.lens(200) is None
    assert lib.lens(0) is None


def test_framing_carries_the_declared_meaning(lib) -> None:
    """Establishing sets geography; close-up carries thought."""

    carries = {frame.name: frame.carries for frame in lib.framing()}
    assert carries == {
        "establishing shot": "sets geography",
        "medium shot": "carries action",
        "close-up": "carries thought",
        "extreme close-up": "isolates a decision",
    }
    assert len(FRAMES) == 4


def test_angles_create_the_declared_effect(lib) -> None:
    creates = {angle.name: angle.creates for angle in lib.angles()}
    assert creates == {
        "low angle": "presence",
        "high angle": "vulnerability",
        "centered symmetry": "authority",
    }
    assert len(ANGLES) == 3


def test_light_roles_and_the_haze_constraint(lib) -> None:
    roles = {light.name: light.role for light in lib.lighting()}
    assert roles == {
        "key light": "establishes intention",
        "rim light": "separates the subject",
        "practical lights": "establish world",
        "volumetric haze": "reveals depth",
    }
    haze = next(light for light in LIGHTS if light.name == "volumetric haze")
    assert "never as decoration" in haze.constraint


def test_time_qualities_support_the_declared_tones(lib) -> None:
    supports = {quality.name: quality.supports for quality in lib.time_qualities()}
    assert supports == {
        "blue hour": "reflection",
        "hard noon": "discipline",
        "warm side light": "legacy",
    }
    assert len(TIME_QUALITIES) == 3


def test_the_five_motivations_are_exactly_the_bibles_list(lib) -> None:
    """"Every camera movement must have motivation: reveal, approach, escape,
    observation or transformation."""

    assert [motivation.name for motivation in lib.motivations()] == [
        "reveal",
        "approach",
        "escape",
        "observation",
        "transformation",
    ]
    assert len(MOTIVATIONS) == 5


def test_every_rule_cites_its_source(lib) -> None:
    findings = lib.audit_style(_style())
    assert findings
    assert all(finding.source.endswith("CINEMATIC_BIBLE.md") for finding in findings)
    assert all(finding.rule for finding in findings)


# -------------------------------------------------------------------- lookups


@pytest.mark.parametrize(
    "purpose,expected",
    [("isolation", [135]), ("vulnerability", [24]), ("luxury", [85]), ("architecture", [24]), ("movement", [35])],
)
def test_lens_for_finds_the_focal_length_that_serves_a_purpose(lib, purpose, expected) -> None:
    assert [profile.focal_mm for profile in lib.lens_for(purpose)] == expected


def test_lens_for_an_unknown_purpose_is_empty(lib) -> None:
    assert lib.lens_for("explosions") == []
    assert lib.lens_for("") == []


@pytest.mark.parametrize(
    "text,expected",
    [
        ("85mm portrait compression", 85),
        ("40mm large format", None),  # not in the Bible's lens language
        ("24mm wide", 24),
        ("135mm macro-like compression", 135),
        ("no lens named", None),
        ("", None),
    ],
)
def test_focal_of_reads_a_focal_length_out_of_free_text(lib, text, expected) -> None:
    assert lib.focal_of(text) == expected


def test_framing_and_angle_are_detected_in_direction_text(lib) -> None:
    assert lib.frame_of("wide establishing shot").name == "establishing shot"
    assert lib.frame_of("intimate close-up").name == "close-up"
    assert lib.angle_of("low-angle tracking").name == "low angle"
    assert lib.angle_of("centered frame, locked tripod").name == "centered symmetry"
    assert lib.frame_of("a beautiful shot") is None
    assert lib.frame_of("") is None


def test_lights_and_qualities_are_detected_in_lighting_text(lib) -> None:
    lights = lib.lights_in("hard practical sources, wet reflective floors")
    assert [light.name for light in lights] == ["practical lights"]
    assert [light.name for light in lib.lights_in("soft volumetric key, gentle rim separation")] == [
        "key light",
        "rim light",
        "volumetric haze",
    ]
    assert lib.qualities_in("consistent blue-hour lighting")[0].name == "blue hour"
    assert lib.lights_in("available light") == []


@pytest.mark.parametrize(
    "support,expected",
    [("legacy", "warm side light"), ("discipline", "hard noon"), ("reflection", "blue hour")],
)
def test_light_for_maps_a_tone_to_its_quality(lib, support, expected) -> None:
    assert lib.light_for(support).name == expected


def test_light_for_an_unknown_tone_is_none(lib) -> None:
    assert lib.light_for("chaos") is None
    assert lib.light_for("") is None


# --------------------------------------------------------------- motivation


def test_a_named_motivation_is_recognised(lib) -> None:
    assert lib.motivation_of("slow monumental push-in") == ("approach",)
    assert lib.motivation_of("full orbit around a locked subject") == ("observation",)
    assert lib.motivation_of("crane up and away") == ("reveal", "escape")


def test_a_still_camera_owes_no_motivation(lib) -> None:
    """The Bible constrains camera **movement**; stillness has nothing to justify."""

    for motion in ("static", "none", ""):
        assert lib.is_still(motion) is True
        assert lib.is_motivated(motion) is True, f'"{motion}" must not be flagged as unmotivated'
        assert lib.motivation_of(motion) == ()


def test_a_movement_with_no_named_motivation_is_flagged(lib) -> None:
    assert lib.is_still("sudden zoom") is False
    assert lib.motivation_of("sudden zoom") == ()
    assert lib.is_motivated("sudden zoom") is False


def test_claiming_motivation_without_naming_one_is_attention_not_a_violation(lib) -> None:
    assert lib.claims_motivation_without_naming("motivated, steady") is True
    finding = next(
        item for item in lib.audit_style(_style(camera_motion="motivated, steady")) if item.rule == RULE_MOTION_MOTIVATED
    )
    assert finding.status == STATUS_ATTENTION
    assert "without naming one" in finding.detail


# ------------------------------------------------------------------ the rules


def test_a_clean_style_passes_every_rule(lib) -> None:
    findings = lib.audit_style(_style())
    assert {finding.rule for finding in findings} == {
        RULE_GRAIN_SUBTLE,
        RULE_PROTECT_HIGHLIGHTS,
        RULE_TEAL_AMBER_SPARINGLY,
        RULE_MOTION_MOTIVATED,
        RULE_HAZE_HAS_PURPOSE,
        RULE_LENS_DECLARED,
        RULE_SKIN_NATURAL,
    }
    assert all(finding.status == STATUS_OK for finding in findings), [f.to_dict() for f in findings]


def test_loud_grain_is_flagged(lib) -> None:
    finding = next(item for item in lib.audit_style(_style(grain="heavy 16mm grain")) if item.rule == RULE_GRAIN_SUBTLE)
    assert finding.status == STATUS_ATTENTION


def test_clipping_language_is_flagged_unless_protection_is_declared(lib) -> None:
    flagged = next(
        item
        for item in lib.audit_style(_style(contrast="crushed blacks, specular highlights"))
        if item.rule == RULE_PROTECT_HIGHLIGHTS
    )
    assert flagged.status == STATUS_ATTENTION
    protected = next(
        item
        for item in lib.audit_style(_style(lut="crushed blacks, protected highlights"))
        if item.rule == RULE_PROTECT_HIGHLIGHTS
    )
    assert protected.status == STATUS_OK


def test_the_teal_and_amber_pair_is_flagged_unless_restraint_is_declared(lib) -> None:
    loud = next(
        item
        for item in lib.audit_style(_style(palette="punchy teal-orange", lut="blockbuster"))
        if item.rule == RULE_TEAL_AMBER_SPARINGLY
    )
    assert loud.status == STATUS_ATTENTION

    restrained = next(
        item
        for item in lib.audit_style(_style(palette="teal and amber restraint", lut="neutral"))
        if item.rule == RULE_TEAL_AMBER_SPARINGLY
    )
    assert restrained.status == STATUS_OK, "a palette that declares restraint already satisfies 'sparingly'"


def test_decorative_haze_is_flagged(lib) -> None:
    decorative = next(
        item
        for item in lib.audit_style(_style(particles="thick atmospheric haze", lighting="soft key"))
        if item.rule == RULE_HAZE_HAS_PURPOSE
    )
    assert decorative.status == STATUS_ATTENTION
    purposeful = next(
        item
        for item in lib.audit_style(_style(particles="dust in shafts of light", lighting="volumetric haze"))
        if item.rule == RULE_HAZE_HAS_PURPOSE
    )
    assert purposeful.status == STATUS_OK


def test_a_shot_without_a_known_focal_length_is_flagged(lib) -> None:
    findings = lib.audit_shot(_shot(lens="anamorphic"))
    assert next(item for item in findings if item.rule == RULE_LENS_DECLARED).status == STATUS_ATTENTION
    ok = lib.audit_shot(_shot(lens="50mm"))
    assert next(item for item in ok if item.rule == RULE_LENS_DECLARED).status == STATUS_OK


def test_a_shot_with_an_unmotivated_move_is_a_violation(lib) -> None:
    finding = next(item for item in lib.audit_shot(_shot(camera_path="sudden zoom")) if item.rule == RULE_MOTION_MOTIVATED)
    assert finding.status == STATUS_VIOLATION


# ------------------------------------------------------------- library audit


def test_the_library_audit_reports_its_own_exceptions(lib) -> None:
    """The seeds are not silently exempt: real exceptions are surfaced."""

    report = lib.audit_library(list(SEED_STYLES), list(SEED_SHOTS))
    assert report["styles_audited"] == 7
    assert report["shots_audited"] == 10
    assert set(report["flagged"]) <= {style.style_id for style in SEED_STYLES} | {shot.code for shot in SEED_SHOTS}
    assert "marvel-trailer" in report["flagged"], "teal-orange blockbuster leans on the pair"
    assert report["compliant"], "the audit must not flag everything"
    assert len(report["compliant"]) + len(report["flagged"]) == 17


def test_the_audit_finds_no_false_violations_in_the_seeds(lib) -> None:
    """Every seed finding is attention, never a violation.

    Pinned so that tightening a keyword set cannot quietly start condemning the
    published library.
    """

    report = lib.audit_library(list(SEED_STYLES), list(SEED_SHOTS))
    for identifier, items in report["flagged"].items():
        for item in items:
            assert item["status"] == STATUS_ATTENTION, f"{identifier}: {item}"


def test_the_neutral_fallback_is_not_condemned_for_being_inert(lib) -> None:
    neutral = next(style for style in SEED_STYLES if style.style_id == "brobond-neutral")
    findings = lib.audit_style(neutral)
    motion = next(item for item in findings if item.rule == RULE_MOTION_MOTIVATED)
    assert motion.status == STATUS_OK
    assert "no movement" in motion.detail


def test_the_audit_works_without_shots(lib) -> None:
    report = lib.audit_library(list(SEED_STYLES))
    assert report["shots_audited"] == 0


# ---------------------------------------------------------- episode cohesion


def test_grain_drift_across_an_episode_is_a_violation(lib) -> None:
    report = lib.episode_consistency([_style(grain="none"), _style(grain="subtle 35mm grain")])
    assert report["consistent"] is False
    violation = next(item for item in report["findings"] if item["rule"] == RULE_GRAIN_CONSISTENT)
    assert violation["status"] == STATUS_VIOLATION
    assert report["grain"] == ["none", "subtle 35mm grain"]


def test_a_consistent_episode_reports_no_findings(lib) -> None:
    report = lib.episode_consistency([_style(), _style(), _style()])
    assert report["consistent"] is True
    assert report["scenes"] == 3
    assert report["findings"] == []


def test_grade_and_palette_drift_are_attention_not_violation(lib) -> None:
    report = lib.episode_consistency([_style(lut="neutral filmic"), _style(lut="cold teal grade")])
    assert report["consistent"] is True, "only grain breaks consistency outright"
    assert [item["status"] for item in report["findings"]] == [STATUS_ATTENTION]


def test_an_empty_episode_is_trivially_consistent(lib) -> None:
    report = lib.episode_consistency([])
    assert report == {"scenes": 0, "consistent": True, "grain": [], "lut": [], "palette": [], "findings": []}


def test_the_real_library_is_internally_inconsistent_across_styles(lib) -> None:
    """Different styles are different grades; that is expected, and the report says so."""

    john_wick = next(style for style in SEED_STYLES if style.style_id == "john-wick")
    neo_tokyo = next(style for style in SEED_STYLES if style.style_id == "neo-tokyo")
    assert lib.episode_consistency([john_wick, neo_tokyo])["consistent"] is False
    assert lib.episode_consistency([john_wick, john_wick])["consistent"] is True


# --------------------------------------------------------------- explanation


def test_explain_speaks_the_grammar_not_the_prompt(lib) -> None:
    text = lib.explain(_style(lens="85mm portrait", lighting="warm side light, soft key", camera_motion="slow dolly-in"))
    assert "85mm for portrait, luxury, compression, separation" in text
    assert "warm side light supports legacy" in text
    assert "motivated by approach" in text


def test_explain_says_so_when_a_move_has_no_motivation(lib) -> None:
    assert "declares no motivation" in lib.explain(_style(camera_motion="sudden zoom"))


def test_explain_handles_a_lens_outside_the_language(lib) -> None:
    text = lib.explain(_style(lens="40mm large format"))
    assert text.startswith("40mm large format")


# ----------------------------------------------------------------- boundaries


def test_the_library_never_produces_prompt_text(lib) -> None:
    """The PromptCompiler owns text. The library describes and judges."""

    assert not hasattr(lib, "compile")
    assert not hasattr(lib, "build")
    assert not hasattr(lib, "enhance")
    assert "cinematic composition" not in lib.explain(_style())


def test_the_library_does_not_recommend_styles(lib) -> None:
    """Style choice belongs to DirectorAgent; the library has no opinion."""

    assert not hasattr(lib, "recommend")
    assert not hasattr(lib, "style_for")
    assert not hasattr(lib, "direct")


def test_the_library_reads_presets_without_mutating_them(lib) -> None:
    style = _style()
    before = style.to_dict()
    lib.audit_style(style)
    lib.explain(style)
    assert style.to_dict() == before


def test_findings_are_serialisable(lib) -> None:
    finding = lib.audit_style(_style())[0]
    payload = finding.to_dict()
    assert set(payload) == {"rule", "status", "detail", "source"}
    assert isinstance(payload["rule"], str)


def test_profiles_are_serialisable(lib) -> None:
    assert lib.lens(24).to_dict()["semantics"] == ["scale", "environment", "vulnerability", "architecture"]
    assert isinstance(lib.framing()[0].to_dict()["keywords"], list)
    assert lib.motivations()[0].to_dict()["name"] == "reveal"
    assert lib.time_qualities()[0].to_dict()["supports"] == "reflection"
