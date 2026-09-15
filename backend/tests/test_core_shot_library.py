"""ETAPA 6 — the 300-shot library.

Three things are pinned here: the ten published presets are untouched, the
library reaches the target SHOT_LIBRARY.md declares, and every one of the 300
entries obeys the CINEMATIC_BIBLE grammar from ETAPA 5.
"""
import pytest

from app.core.cinematic_library import LENSES, MOTIVATIONS
from app.core.contracts import ShotPreset
from app.core.shot_library import (
    EXPANDED_SHOTS,
    FAMILIES,
    FAMILY_LABELS,
    FULL_SHOT_LIBRARY,
    LIBRARY_TARGET,
    PUBLISHED_CODES,
    ShotLibrary,
    build_shot,
)
from app.core.shot_resolver import SEED_SHOTS


@pytest.fixture()
def lib() -> ShotLibrary:
    return ShotLibrary()


# ------------------------------------------------------------------- the target


def test_the_library_reaches_the_published_target(lib) -> None:
    """SHOT_LIBRARY.md: "The full library target is 300+ shots"."""

    assert LIBRARY_TARGET == 300
    assert lib.count() == 300
    assert lib.audit()["meets_target"] is True


def test_the_library_is_ten_published_plus_290_expanded(lib) -> None:
    assert len(SEED_SHOTS) == 10, "the published seeds must not change size"
    assert len(EXPANDED_SHOTS) == 290
    assert len(FULL_SHOT_LIBRARY) == 300


def test_the_published_presets_come_first_and_unchanged(lib) -> None:
    assert FULL_SHOT_LIBRARY[:10] == SEED_SHOTS


# ------------------------------------------------- preservation of what existed


def test_the_published_shots_keep_their_original_nine_fields() -> None:
    """Byte-level preservation: the expansion never rewrites a stable identifier."""

    hero = next(shot for shot in FULL_SHOT_LIBRARY if shot.code == "SH001")
    assert (hero.name, hero.lens, hero.camera_path) == (
        "Hero Walk",
        "50mm",
        "low-angle tracking, moving with the subject",
    )
    assert hero.intention == "confident forward motion"

    insert = next(shot for shot in FULL_SHOT_LIBRARY if shot.code == "SH122")
    assert insert.lens == "135mm", "the 135mm that ETAPA 5 fixed must stay 135mm"


def test_the_published_shots_are_not_given_invented_expansion_fields() -> None:
    """SHOT_LIBRARY.md does not state a shot size for all ten, so none is invented."""

    for shot in SEED_SHOTS:
        assert shot.frame == "", f"{shot.code} was given an invented frame"
        assert shot.lighting == "", f"{shot.code} was given an invented lighting"
        assert shot.continuity == "", f"{shot.code} was given an invented continuity"
        assert shot.family == "", f"{shot.code} was assigned to a family"


def test_published_codes_are_reserved(lib) -> None:
    assert PUBLISHED_CODES == {
        "SH001", "SH014", "SH032", "SH051", "SH089", "SH120", "SH121", "SH122", "SH123", "SH124",
    }
    expanded_codes = {shot.code for shot in EXPANDED_SHOTS}
    assert not (expanded_codes & PUBLISHED_CODES), "the expansion must never reuse a stable identifier"


def test_no_code_is_used_twice(lib) -> None:
    assert lib.duplicates() == []
    codes = [shot.code for shot in FULL_SHOT_LIBRARY]
    assert len(codes) == len(set(codes)) == 300


def test_no_name_is_used_twice(lib) -> None:
    names = [shot.name.casefold() for shot in FULL_SHOT_LIBRARY]
    assert len(names) == len(set(names)) == 300


def test_every_code_lives_in_the_declared_space(lib) -> None:
    for shot in FULL_SHOT_LIBRARY:
        assert shot.code.startswith("SH"), shot.code
        number = int(shot.code[2:])
        assert 1 <= number <= 300, shot.code


# ------------------------------------------------------------- Bible compliance


def test_every_shot_obeys_the_cinematic_bible(lib) -> None:
    """The whole point of ETAPA 5's grammar: a 300-entry library stays honest."""

    assert lib.violations() == {}


def test_every_shot_uses_a_declared_focal_length(lib) -> None:
    declared = {profile.focal_mm for profile in LENSES}
    for shot in FULL_SHOT_LIBRARY:
        assert lib.grammar.focal_of(shot.lens) in declared, f"{shot.code}: {shot.lens}"


def test_every_movement_names_a_motivation_or_is_still(lib) -> None:
    """"Every camera movement must have motivation."

    This is the rule the first draft failed on: SH087 said "crane descent" and
    the grammar only knew "descend"/"descending". The grammar was widened rather
    than the shot reworded, so the checker is not being gamed.
    """

    for shot in FULL_SHOT_LIBRARY:
        assert lib.grammar.motivation_of(shot.camera_path) or lib.grammar.is_still(shot.camera_path), (
            f"{shot.code}: '{shot.camera_path}'"
        )


def test_the_descent_noun_form_is_recognised(lib) -> None:
    """Regression for the SH087 gap."""

    assert lib.grammar.motivation_of("crane descent following the fall") == ("reveal",)
    assert lib.get("SH087") is not None


def test_every_expanded_shot_declares_the_fields_the_policy_requires(lib) -> None:
    """"New shots require code, name, lens, frame, movement, lighting, emotional
    intention and continuity notes." — SHOT_LIBRARY.md, Expansion policy."""

    for shot in EXPANDED_SHOTS:
        for field_name in ("code", "name", "lens", "frame", "camera_path", "lighting", "intention", "continuity"):
            assert getattr(shot, field_name), f"{shot.code} is missing {field_name}"


def test_every_frame_is_a_known_shot_size(lib) -> None:
    known = {frame.name for frame in lib.grammar.framing()}
    for shot in EXPANDED_SHOTS:
        assert shot.frame in known, f"{shot.code}: {shot.frame}"


def test_omitting_a_required_field_on_a_new_shot_is_caught() -> None:
    """The exemption for the published ten must not become a loophole."""

    broken = build_shot(
        ("SH901", "Incomplete", 50, "medium shot", "slow dolly advance", "", "something", ""),
        "test",
    )
    violations = ShotLibrary((broken,)).violations()
    assert set(violations["SH901"]) >= {"lighting is required on a new shot", "continuity is required on a new shot"}


def test_a_published_shot_is_exempt_from_the_new_field_rule() -> None:
    assert ShotLibrary(SEED_SHOTS).violations() == {}


# ------------------------------------------------------------------- derivation


def test_depth_follows_the_shot_size(lib) -> None:
    assert lib.get("SH002").depth.startswith("deep"), "an establishing shot must keep geography legible"
    assert "extremely shallow" in lib.get("SH133").depth
    assert "shallow" in lib.get("SH104").depth


def test_focus_follows_the_shot_size(lib) -> None:
    assert "deep focus" in lib.get("SH002").focus
    assert "razor thin" in lib.get("SH133").focus


def test_a_locked_tripod_never_shakes(lib) -> None:
    for shot in FULL_SHOT_LIBRARY:
        if "locked tripod" in shot.camera_path or "static" in shot.speed:
            assert shot.shake.startswith("none"), f"{shot.code}: {shot.shake}"


def test_handheld_is_the_only_declared_shake(lib) -> None:
    for shot in EXPANDED_SHOTS:
        if shot.shake != "none" and not shot.shake.startswith("none,"):
            assert shot.shake == "motivated handheld", f"{shot.code}: {shot.shake}"
            assert "handheld" in shot.camera_path, f"{shot.code} shakes without saying why"


def test_a_static_shot_reports_a_static_speed(lib) -> None:
    assert lib.get("SH027").speed == "static"
    assert lib.get("SH107").speed == "static"


def test_a_fast_move_reports_a_fast_speed(lib) -> None:
    assert lib.get("SH205").speed == "fast, controlled"


# -------------------------------------------------------------------- browsing


def test_families_cover_the_whole_library(lib) -> None:
    assert lib.families() == FAMILIES
    assert set(FAMILY_LABELS) == set(FAMILIES)
    counts = lib.family_counts()
    assert counts["published"] == 10
    assert sum(counts.values()) == 300


def test_each_family_is_substantial(lib) -> None:
    """No family is a token entry: each carries at least 24 shots."""

    for family in FAMILIES:
        assert len(lib.by_family(family)) >= 24, family


def test_lens_coverage_is_balanced(lib) -> None:
    counts = {profile.focal_mm: len(lib.by_lens(profile.focal_mm)) for profile in LENSES}
    assert sum(counts.values()) == 300
    assert min(counts.values()) >= 50, counts


def test_frame_coverage_spans_all_four_sizes(lib) -> None:
    for frame in lib.grammar.framing():
        assert len(lib.by_frame(frame.name)) >= 50, frame.name


def test_motivation_coverage_is_reported_honestly(lib) -> None:
    """`transformation` is genuinely rare in this library; the number is exposed,
    not hidden, because a director searching for it must know how thin it is."""

    counts = {motivation.name: len(lib.by_motivation(motivation.name)) for motivation in MOTIVATIONS}
    assert counts["transformation"] < 10
    assert counts["observation"] > 100
    assert lib.audit()["total"] == 300


def test_search_spans_code_name_family_intention_and_continuity(lib) -> None:
    assert lib.search("SH300")[0].code == "SH300"
    assert lib.search("Final Survey")[0].code == "SH300"
    assert lib.search("documentary"), "family is searchable"
    assert lib.search("grief"), "intention is searchable"
    assert lib.search("eyeline"), "continuity notes are searchable"


def test_an_unknown_query_returns_nothing(lib) -> None:
    assert lib.search("zzzz-no-match") == []


def test_an_empty_query_returns_the_whole_library(lib) -> None:
    assert len(lib.search("")) == 300
    assert len(lib.all()) == 300


def test_lookup_is_case_insensitive(lib) -> None:
    assert lib.get("sh300").code == "SH300"
    assert lib.get("  SH300  ").code == "SH300"
    assert lib.get("SH999") is None


# ------------------------------------------------------------------ validation


def test_a_violation_is_reported_against_its_code() -> None:
    broken = build_shot(
        ("SH902", "Bad Lens", 200, "medium shot", "slow dolly advance", "soft key", "x", "y"),
        "test",
    )
    violations = ShotLibrary((broken,)).violations()
    assert "lens '200mm' is not in the lens language" in violations["SH902"]


def test_an_unknown_frame_is_reported() -> None:
    broken = build_shot(
        ("SH905", "Odd Frame", 50, "two shot", "slow dolly advance", "soft key", "x", "y"),
        "test",
    )
    assert "frame 'two shot' is not a known shot size" in ShotLibrary((broken,)).violations()["SH905"]


def test_a_shot_without_an_intention_is_reported() -> None:
    broken = build_shot(
        ("SH906", "No Purpose", 50, "medium shot", "slow dolly advance", "soft key", "", "y"),
        "test",
    )
    assert "no emotional intention declared" in ShotLibrary((broken,)).violations()["SH906"]


def test_an_unmotivated_move_is_reported() -> None:
    broken = build_shot(
        ("SH903", "No Reason", 50, "medium shot", "sudden zoom", "soft key", "x", "y"),
        "test",
    )
    assert any("names no motivation" in issue for issue in ShotLibrary((broken,)).violations()["SH903"])


def test_a_duplicate_code_is_reported() -> None:
    a = build_shot(("SH904", "First", 50, "medium shot", "slow dolly advance", "k", "i", "c"), "test")
    b = build_shot(("SH904", "Second", 50, "medium shot", "slow dolly advance", "k", "i", "c"), "test")
    assert ShotLibrary((a, b)).duplicates() == ["SH904"]


def test_the_audit_reports_size_and_compliance(lib) -> None:
    report = lib.audit()
    assert report["total"] == 300
    assert report["target"] == 300
    assert report["published"] == 10
    assert report["expanded"] == 290
    assert report["violations"] == {}
    assert report["duplicates"] == []


# ---------------------------------------------------------------- presentation


def test_describe_includes_the_expansion_fields(lib) -> None:
    line = lib.describe(lib.get("SH300"))
    assert line.startswith("SH300 Final Survey")
    assert "[documentary]" in line
    assert "light: natural available light" in line
    assert "continuity: must echo SH283's survey" in line


def test_describe_of_a_published_shot_omits_empty_fields(lib) -> None:
    line = lib.describe(lib.get("SH001"))
    assert line.startswith("SH001 Hero Walk")
    assert "light:" not in line, "an empty field must not render as an empty label"
    assert "continuity:" not in line


def test_as_directable_carries_the_grammar(lib) -> None:
    payload = lib.as_directable(lib.get("SH300"))
    assert payload["lens_mm"] == 24
    assert payload["motivations"] == ["reveal", "escape"]
    assert payload["code"] == "SH300"


def test_presets_are_frozen(lib) -> None:
    with pytest.raises(Exception):
        lib.get("SH300").name = "outro"  # type: ignore[misc]


def test_the_library_is_read_only_over_its_presets(lib) -> None:
    """The library queries and judges; it never rewrites a preset."""

    assert not hasattr(lib, "register")
    assert not hasattr(lib, "add")
    assert not hasattr(lib, "update")


def test_a_shot_is_a_value_object(lib) -> None:
    assert isinstance(lib.get("SH300"), ShotPreset)


def test_continuity_notes_reference_other_shots_consistently(lib) -> None:
    """Continuity is the point of the field: notes must name what to match."""

    referenced = [
        shot.continuity
        for shot in EXPANDED_SHOTS
        if "SH" in shot.continuity
    ]
    assert len(referenced) >= 20, "continuity notes should tie shots together"
    codes_in_library = {shot.code for shot in FULL_SHOT_LIBRARY}
    for shot in EXPANDED_SHOTS:
        for token in shot.continuity.replace(",", " ").replace(".", " ").split():
            if token.startswith("SH") and token[2:].isdigit():
                assert token in codes_in_library, f"{shot.code} references unknown {token}"
