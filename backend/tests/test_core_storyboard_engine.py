"""ETAPA 8 tests — the storyboard engine.

The engine exists because of three defects verified before it was written:
`SceneBeat.shot_code` was None for every scene, the lighting was the same string
in every beat, and the movement placeholder "motivated by the beat" was flagged
by the very grammar the Director uses to judge it.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from app.core import ARC_BY_FORMAT, CinematicLibrary, DirectorAgent, ShotLibrary
from app.core import Storyboard, StoryboardEngine, StoryboardShot
from app.core.cinematic_library import MOTIVATIONS
from app.core.contracts import SceneBeat
from app.core.shot_library import EXPANDED_SHOTS, FULL_SHOT_LIBRARY

BRIEF = "Quero um comercial de 30 segundos para uma camiseta artesanal."
FULL_CODES = {shot.code for shot in FULL_SHOT_LIBRARY}
EXPANDED_CODES = {shot.code for shot in EXPANDED_SHOTS}
MOTIVATION_NAMES = {motivation.name for motivation in MOTIVATIONS}


@pytest.fixture()
def engine() -> StoryboardEngine:
    return StoryboardEngine(
        director=DirectorAgent(), shots=ShotLibrary(), grammar=CinematicLibrary()
    )


# ---------------------------------------------------------------------------
# The defect it exists to fix: beats were never cast
# ---------------------------------------------------------------------------


def test_every_scene_names_a_real_shot_from_the_library(engine):
    board = engine.build(BRIEF, scene_count=5)
    for shot in board.shots:
        assert shot.shot_code, "a scene with no shot is exactly the gap this etapa closes"
        assert shot.shot_code in FULL_CODES


def test_the_cast_comes_from_the_expanded_library_not_the_brief(engine):
    """Codes come from the library, never invented out of the request text."""

    board = engine.build(BRIEF, scene_count=6)
    assert all(code.startswith("SH") for code in board.shot_codes)
    assert all(code in EXPANDED_CODES for code in board.shot_codes)


def test_the_beats_projected_back_carry_a_shot_code(engine):
    """`as_beats` is what makes the 300-shot library reachable downstream."""

    beats = engine.as_beats(engine.build(BRIEF, scene_count=4))
    assert all(isinstance(beat, SceneBeat) for beat in beats)
    assert all(beat.shot_code for beat in beats)
    assert all(beat.shot_code in FULL_CODES for beat in beats)


def test_a_cast_beat_carries_the_shot_lighting_not_a_placeholder(engine):
    board = engine.build(BRIEF, scene_count=5)
    assert "consistent blue-hour lighting" not in {shot.lighting for shot in board.shots}
    assert all(shot.lighting for shot in board.shots)


# ---------------------------------------------------------------------------
# Narrative arcs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("scene_count", "arc"),
    [
        (2, ("establishing", "resolution")),
        (3, ("establishing", "introduction", "resolution")),
        (4, ("establishing", "introduction", "product", "resolution")),
        (5, ("establishing", "introduction", "product", "product", "resolution")),
        (
            8,
            (
                "establishing",
                "introduction",
                "product",
                "product",
                "product",
                "product",
                "product",
                "resolution",
            ),
        ),
    ],
)
def test_the_arc_obeys_the_three_act_shape(engine, scene_count, arc):
    assert engine.arc_for("commercial", scene_count) == arc


def test_opening_and_closing_always_anchor_the_arc(engine):
    for format_name in ARC_BY_FORMAT:
        for scene_count in range(2, 13):
            arc = engine.arc_for(format_name, scene_count)
            assert len(arc) == scene_count
            assert arc[0] == "establishing", f"{format_name} must open on geography"
            assert arc[-1] == "resolution", f"{format_name} must close on a resolution"


def test_shorter_sequences_trim_from_the_middle_not_the_ends(engine):
    arc = engine.arc_for("commercial", 3)
    assert arc[0] == "establishing"
    assert arc[-1] == "resolution"


def test_the_families_in_an_arc_are_real_families(engine):
    library = ShotLibrary()
    known = set(library.families())
    for format_name in ARC_BY_FORMAT:
        for family in engine.arc_for(format_name, 8):
            assert family in known, f"'{family}' is not a family in the library"


def test_a_one_scene_sequence_is_reported_not_raised(engine):
    """The engine reports; the API layer is what refuses a bad request."""

    board = engine.build(BRIEF, scene_count=1)
    report = engine.validate(board)
    assert board.scene_count == 1
    assert not report["valid"]
    assert any(finding["rule"] == "scene-count" for finding in report["violations"])


def test_a_runaway_sequence_is_reported_with_its_real_cost(engine):
    board = engine.build(BRIEF, scene_count=40)
    report = engine.validate(board)
    assert board.scene_count == 40
    assert not report["valid"]
    assert any(finding["rule"] == "runtime" for finding in report["violations"])
    assert any(finding["rule"] == "no-repeat-cut" for finding in report["violations"])


def test_the_documentary_arc_is_reachable(engine):
    """ETAPA 7 closed the gap this test used to pin as a known defect.

    `FORMAT_KEYWORDS` folded "documentário"/"documentario" into `film`, so
    `detect_format` could never return "documentary" and the engine's
    documentary arc was dead code. Both languages now resolve to it and the arc
    actually casts documentary shots.
    """

    assert "documentary" in ARC_BY_FORMAT
    assert "documentary" in DirectorAgent().FORMAT_KEYWORDS
    assert DirectorAgent().detect_format("documentário sobre artesãos locais") == "documentary"
    assert DirectorAgent().detect_format("a documentary about local artisans") == "documentary"


def test_a_documentary_brief_casts_the_documentary_arc(engine):
    """The arc is reachable *and* used: 24 documentary presets exist for it."""

    board = engine.build("documentário sobre artesãos locais", scene_count=5)
    assert board.format == "documentary"
    assert [shot.family for shot in board.shots] == list(ARC_BY_FORMAT["documentary"])
    documentary_shots = [s for s in engine.shots.all() if s.family == "documentary"]
    assert documentary_shots, "the arc would be casting from an empty family"


def test_documentary_and_film_stay_apart(engine):
    """A trailer is still a film; only documentary language moves it."""

    assert engine.build("um trailer de cinema", scene_count=5).format == "film"
    assert engine.build("um curta de ficção", scene_count=5).format == "film"


def test_formats_exposes_every_arc_the_engine_knows(engine):
    assert set(engine.formats()) == set(ARC_BY_FORMAT)


# ---------------------------------------------------------------------------
# Variety — a sequence must not collapse onto two shots
# ---------------------------------------------------------------------------


def test_a_long_sequence_does_not_alternate_between_two_shots(engine):
    """Regression: the first draft reused the same pair across 12 scenes."""

    board = engine.build(BRIEF, scene_count=12)
    assert len(set(board.shot_codes)) == 12


def test_no_two_neighbouring_scenes_use_the_same_shot(engine):
    for scene_count in range(2, 13):
        codes = engine.build(BRIEF, scene_count=scene_count).shot_codes
        assert all(a != b for a, b in zip(codes, codes[1:]))


def test_the_same_brief_always_casts_the_same_sequence(engine):
    """Determinism matters: a storyboard has to be reproducible for a review."""

    first = engine.build(BRIEF, scene_count=6).shot_codes
    second = engine.build(BRIEF, scene_count=6).shot_codes
    assert first == second


def test_a_different_brief_casts_a_different_sequence(engine):
    assert engine.build(BRIEF, scene_count=5).shot_codes != engine.build(
        "Um curta-metragem sobre um astronauta perdido em Marte.", scene_count=5
    ).shot_codes


# ---------------------------------------------------------------------------
# Continuity and lens progression
# ---------------------------------------------------------------------------


def test_lighting_is_not_the_same_string_in_every_scene(engine):
    board = engine.build(BRIEF, scene_count=6)
    assert len({shot.lighting for shot in board.shots}) > 1


def test_a_scene_tells_the_next_what_to_match(engine):
    board = engine.build(BRIEF, scene_count=4)
    assert all(shot.continuity for shot in board.shots)
    assert board.shots[0].continuity == (
        "establish geography once; later scenes inherit this light"
    )
    assert board.shots[0].continuity != board.shots[1].continuity


def test_the_lens_progression_runs_wide_to_tight_and_back(engine):
    board = engine.build(BRIEF, scene_count=5)
    assert board.lens_progression[0] == "24mm"
    assert board.lens_progression[-1] == "24mm"
    assert "85mm" in board.lens_progression


def test_runtime_is_the_sum_of_the_scenes(engine):
    board = engine.build(BRIEF, scene_count=4, duration_per_scene=2.5)
    assert board.runtime_seconds == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# Validation against the cinematic grammar
# ---------------------------------------------------------------------------


def test_a_cast_storyboard_passes_the_grammar(engine):
    for scene_count in range(2, 13):
        report = engine.validate(engine.build(BRIEF, scene_count=scene_count))
        assert report["valid"], f"{scene_count} scenes: {report['violations']}"
        assert report["violations"] == []


def test_the_movement_names_a_real_motivation(engine):
    """Before: "motivated by the beat" drew an `attention` from the grammar."""

    board = engine.build(BRIEF, scene_count=5)
    assert all("motivated by the beat" not in shot.motion for shot in board.shots)
    for shot in board.shots:
        assert all(
            name in MOTIVATION_NAMES for name in shot.motivation.split(", ")
        ), shot.motivation


def test_the_shot_families_cover_the_whole_sequence(engine):
    board = engine.build(BRIEF, scene_count=8)
    assert board.family_sequence == engine.arc_for("commercial", 8)


def test_a_missing_continuity_note_is_reported_as_attention(engine):
    board = engine.build(BRIEF, scene_count=3)
    broken = Storyboard(
        brief=board.brief,
        format=board.format,
        shots=tuple(
            StoryboardShot(**{**shot.to_dict(), "continuity": ""}) for shot in board.shots
        ),
    )
    report = engine.validate(broken)
    assert any(finding["rule"] == "continuity-declared" for finding in report["attention"])
    # A missing note is a warning; it does not by itself invalidate the cut.
    assert report["valid"]


def test_a_repeat_cut_is_reported_as_a_violation(engine):
    board = engine.build(BRIEF, scene_count=2)
    repeated = Storyboard(
        brief=board.brief,
        format=board.format,
        shots=(board.shots[0], board.shots[0]),
    )
    report = engine.validate(repeated)
    assert not report["valid"]
    assert any(finding["rule"] == "no-repeat-cut" for finding in report["violations"])


def test_a_movement_that_names_no_motivation_is_a_violation(engine):
    """No shot in the 300 library trips this — the guard exists for hand-built
    sequences, which is exactly where the Director used to fail its own grammar.
    """

    board = engine.build(BRIEF, scene_count=2)
    unmotivated = Storyboard(
        brief=board.brief,
        format=board.format,
        shots=tuple(
            StoryboardShot(**{**shot.to_dict(), "camera_path": "the camera moves"})
            for shot in board.shots
        ),
    )
    report = engine.validate(unmotivated)
    assert not report["valid"]
    assert len([f for f in report["violations"] if f["rule"] == "motion-motivated"]) == 2


def test_no_shot_in_the_library_trips_the_motivation_guard(engine):
    """The 300 presets were built to satisfy ETAPA 5; assert that still holds."""

    board = engine.build(BRIEF, scene_count=12)
    assert [f["rule"] for f in engine.validate(board)["violations"]] == []


def test_an_overlong_runtime_is_reported_as_a_finding_not_a_crash(engine):
    board = engine.build(BRIEF, scene_count=12, duration_per_scene=30.0)
    findings = {f["rule"]: f for f in engine.validate(board)["violations"]}
    assert findings["runtime"]["detail"] == "360.0s exceeds the 180.0s ceiling"


def test_an_undeclared_lens_is_flagged_not_silently_accepted(engine):
    board = engine.build(BRIEF, scene_count=2)
    odd = Storyboard(
        brief=board.brief,
        format=board.format,
        shots=tuple(
            StoryboardShot(**{**shot.to_dict(), "lens": "17mm"}) for shot in board.shots
        ),
    )
    report = engine.validate(odd)
    assert any(finding["rule"] == "lens-declared" for finding in report["attention"])


def test_a_sequence_that_opens_on_the_product_is_questioned(engine):
    board = engine.build(BRIEF, scene_count=2)
    odd = Storyboard(
        brief=board.brief,
        format=board.format,
        shots=tuple(
            StoryboardShot(**{**shot.to_dict(), "family": "product"}) for shot in board.shots
        ),
    )
    report = engine.validate(odd)
    rules = {finding["rule"] for finding in report["attention"]}
    assert "arc-opens-establishing" in rules
    assert "arc-closes-resolution" in rules


def test_the_report_carries_the_shape_a_director_needs(engine):
    report = engine.validate(engine.build(BRIEF, scene_count=5))
    assert set(report) == {
        "scene_count",
        "runtime_seconds",
        "format",
        "valid",
        "violations",
        "attention",
    }


# ---------------------------------------------------------------------------
# The beat sheet
# ---------------------------------------------------------------------------


def test_the_beat_sheet_is_readable_and_names_every_shot(engine):
    board = engine.build(BRIEF, scene_count=4)
    sheet = engine.beat_sheet(board)
    assert sheet.startswith(f"COMMERCIAL — 4 scenes, {board.runtime_seconds}s")
    for shot in board.shots:
        assert shot.shot_code in sheet
        assert shot.shot_name in sheet
        assert shot.lens in sheet


def test_the_beat_sheet_is_numbered_in_order(engine):
    board = engine.build(BRIEF, scene_count=3)
    lines = engine.beat_sheet(board).splitlines()
    assert len(lines) == 1 + board.scene_count
    assert lines[1].startswith("01. ")
    assert lines[-1].startswith("03. ")


def test_the_beat_sheet_is_not_a_prompt(engine):
    """It is for a director to read, not for a model to consume."""

    sheet = engine.beat_sheet(engine.build(BRIEF, scene_count=3))
    assert "photorealistic" not in sheet
    assert "cinematic composition" not in sheet


# ---------------------------------------------------------------------------
# Boundaries
# ---------------------------------------------------------------------------


def test_the_engine_never_produces_prompt_text(engine):
    """Compiling stays with the PromptCompiler — a boundary the guards protect."""

    board = engine.build(BRIEF, scene_count=3)
    for shot in board.shots:
        for value in shot.to_dict().values():
            if isinstance(value, str):
                assert "photorealistic" not in value
    assert "photorealistic" not in engine.beat_sheet(board)


def test_the_engine_holds_no_shots_of_its_own():
    """Shot data belongs to the library; the engine only reads it."""

    module = pathlib.Path("backend/app/core/storyboard_engine.py").read_text()
    tree = ast.parse(module)
    assigned = {
        target.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    assert not {
        "FULL_SHOT_LIBRARY",
        "EXPANDED_SHOTS",
        "SEED_SHOTS",
        "SHOT_LIBRARY_ROWS",
    } & assigned


def test_the_engine_does_not_reimplement_the_library_rules():
    """Grammar lives in `cinematic_library`; the engine only reports on it."""

    module = pathlib.Path("backend/app/core/storyboard_engine.py").read_text()
    assert "LENSES = " not in module
    assert "FRAME_RULES = " not in module
    assert "def audit(" not in module


def test_the_engine_does_not_reimplement_the_director():
    """Format detection and beat construction stay in `DirectorAgent`."""

    module = pathlib.Path("backend/app/core/storyboard_engine.py").read_text()
    assert "FORMAT_KEYWORDS = " not in module
    assert "def _build_beats" not in module
    assert "def detect_format" not in module


def test_the_engine_is_not_wired_into_the_providers():
    """It is a planning tool; a provider must never receive a storyboard."""

    module = pathlib.Path("backend/app/core/storyboard_engine.py").read_text()
    assert "diffusers" not in module
    assert "subprocess" not in module


def test_a_shot_is_immutable():
    shot = StoryboardShot(
        number=1,
        shot_code="SH002",
        shot_name="City Wakes",
        family="establishing",
        frame="establishing shot",
        lens="24mm",
        camera_path="slow crane reveal descending over the rooftops",
        lighting="blue hour ambience, soft volumetric key",
        motion="slow",
        motivation="reveal",
        intention="place the viewer",
        continuity="establish geography once",
        objective="anchor the setting",
        emotion="calm",
        duration_seconds=5.0,
    )
    assert shot.to_dict()["shot_code"] == "SH002"
    with pytest.raises(Exception):  # noqa: B017 - FrozenInstanceError
        shot.shot_code = "SH003"  # type: ignore[misc]


def test_a_storyboard_recounts_its_scenes(engine):
    board = engine.build(BRIEF, scene_count=7)
    assert board.scene_count == 7 == len(board.shots)
    assert board.to_dict()["scene_count"] == 7
    assert board.to_dict()["shot_codes"] == list(board.shot_codes)


def test_casting_is_not_emotion_aware(engine):
    """Pinned decision: the Director's Portuguese emotions match none of the
    library's English intentions (verified: zero matches across all eight), so a
    token match would be dead code dressed as a feature. The mapping belongs to
    the Director. The set grew from four to eight in ETAPA 7; the invariant that
    matters is the empty `matched` list below, and it still holds.
    """

    from app.core import ShotLibrary

    emotions = {
        beat.emotion
        for brief in (BRIEF, "Um curta-metragem sobre um astronauta perdido em Marte.")
        for count in range(2, 13)
        for beat in DirectorAgent().expand(brief, scene_count=count)
    }
    assert emotions == {
        "curiosidade", "desejo", "convicção", "tensão",
        "reconhecimento", "intimidade", "reverência", "pertencimento",
    }
    intentions = [shot.intention.casefold() for shot in ShotLibrary().all()]
    matched = [
        token
        for emotion in emotions
        for token in emotion.casefold().split()
        if any(token in intention for intention in intentions)
    ]
    assert matched == []


def test_cast_beats_accepts_beats_the_director_already_built(engine):
    """The engine can run after the Director without re-expanding the brief."""

    beats = DirectorAgent().expand(BRIEF, scene_count=4)
    board = engine.cast_beats(beats, brief=BRIEF, format_name="commercial")
    assert board.scene_count == len(beats)
    assert all(shot.shot_code in FULL_CODES for shot in board.shots)
