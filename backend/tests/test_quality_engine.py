"""V3.4 ETAPA 7 — the Quality Engine (Report).

The engine's promise is honesty about provenance: every number in a report
is either **measured** (computed here from the real artifact and the spec)
or **detector** (supplied by the caller), and everything else is listed in
``unmeasured`` — never invented. These tests exercise each heuristic against
real Pillow-generated files, the detector override, the recommendation
plumbing, and the full report shape of ETAPA 3.
"""
from __future__ import annotations

import pathlib

import pytest
from PIL import Image

from app.quality.quality_engine import (
    FIDELITY_MIN_TOKEN_LENGTH,
    LUMINANCE_HIGH,
    LUMINANCE_LOW,
    MediaFacts,
    MOTION_FULL_FPS,
    QUALITY_ENGINE_VERSION,
    QualityEngine,
    RESOLUTION_TARGET_PIXELS,
    SATURATION_LOW,
    SOURCE_DETECTOR,
    SOURCE_MEASURED,
)
from app.quality.quality_rules import STATUS_RETRY
from app.quality.quality_score import (
    CRITERION_COLOR,
    CRITERION_COMPOSITION,
    CRITERION_EYES,
    CRITERION_FACE,
    CRITERION_HANDS,
    CRITERION_LIGHTING,
    CRITERION_MOTION,
    CRITERION_PROMPT_FIDELITY,
    KIND_IMAGE,
    KIND_VIDEO,
    QualityScorer,
    QualityValidationError,
)


@pytest.fixture()
def engine() -> QualityEngine:
    return QualityEngine()


def _image(tmp_path: pathlib.Path, *, size=(1280, 720), color=(128, 100, 160)) -> str:
    target = tmp_path / "render.png"
    Image.new("RGB", size, color).save(target, "PNG")
    return str(target)


def _by_criterion(assessment):
    return {c.criterion: c for c in assessment.breakdown.criteria}


# ---------------------------------------------------------------- input guards


def test_facts_refuse_an_unknown_kind() -> None:
    with pytest.raises(QualityValidationError, match="unknown media kind"):
        MediaFacts(kind="audio")


def test_signals_must_name_a_known_criterion(engine: QualityEngine) -> None:
    facts = MediaFacts(kind=KIND_IMAGE, width=1024, height=1024)
    with pytest.raises(QualityValidationError, match="unknown criterion"):
        engine.assess(facts, signals={"vibe": 50.0})


def test_signals_must_apply_to_the_kind(engine: QualityEngine) -> None:
    facts = MediaFacts(kind=KIND_IMAGE, width=1024, height=1024)
    with pytest.raises(QualityValidationError, match="does not apply"):
        engine.assess(facts, signals={CRITERION_MOTION: 50.0})


def test_signals_must_be_numbers_in_range(engine: QualityEngine) -> None:
    facts = MediaFacts(kind=KIND_IMAGE, width=1024, height=1024)
    with pytest.raises(QualityValidationError, match="must be a number"):
        engine.assess(facts, signals={CRITERION_FACE: "high"})  # type: ignore[dict-item]
    with pytest.raises(QualityValidationError, match="must be a number"):
        engine.assess(facts, signals={CRITERION_FACE: True})  # type: ignore[dict-item]
    with pytest.raises(QualityValidationError, match="outside"):
        engine.assess(facts, signals={CRITERION_FACE: 101.0})


def test_an_asset_nothing_can_be_said_about_is_an_error_not_a_score(engine: QualityEngine) -> None:
    with pytest.raises(QualityValidationError, match="no criterion"):
        engine.assess(MediaFacts(kind=KIND_IMAGE))


# ---------------------------------------------------------------- composition


def test_composition_scores_full_marks_on_exact_geometry(engine: QualityEngine) -> None:
    facts = MediaFacts(
        kind=KIND_IMAGE,
        width=1920,
        height=1080,
        aspect_ratio_expected=16 / 9,
    )
    composition = _by_criterion(engine.assess(facts))[CRITERION_COMPOSITION]
    assert composition.score == 100.0
    assert composition.source == SOURCE_MEASURED


def test_composition_punishes_a_square_render_sold_as_16_9(engine: QualityEngine) -> None:
    right = MediaFacts(kind=KIND_IMAGE, width=1920, height=1080, aspect_ratio_expected=16 / 9)
    wrong = MediaFacts(kind=KIND_IMAGE, width=1080, height=1080, aspect_ratio_expected=16 / 9)
    right_score = _by_criterion(engine.assess(right))[CRITERION_COMPOSITION].score
    wrong_score = _by_criterion(engine.assess(wrong))[CRITERION_COMPOSITION].score
    assert wrong_score < right_score


def test_composition_scales_with_resolution_below_the_target(engine: QualityEngine) -> None:
    small = MediaFacts(kind=KIND_IMAGE, width=RESOLUTION_TARGET_PIXELS // 2, height=RESOLUTION_TARGET_PIXELS // 2)
    large = MediaFacts(kind=KIND_IMAGE, width=RESOLUTION_TARGET_PIXELS, height=RESOLUTION_TARGET_PIXELS)
    assert (
        _by_criterion(engine.assess(small))[CRITERION_COMPOSITION].score
        < _by_criterion(engine.assess(large))[CRITERION_COMPOSITION].score
    )


def test_a_render_below_the_pixel_floor_zeroes_the_resolution_component(engine: QualityEngine) -> None:
    broken = MediaFacts(kind=KIND_IMAGE, width=32, height=32)
    assert _by_criterion(engine.assess(broken))[CRITERION_COMPOSITION].score == 0.0


def test_unreported_geometry_leaves_composition_unmeasured(engine: QualityEngine, tmp_path) -> None:
    # No width/height and no file to probe: composition must be in
    # `unmeasured`, not zero. Prompt fidelity keeps the assessment scoreable.
    facts = MediaFacts(
        kind=KIND_IMAGE,
        prompt_original="golden hour portrait",
        prompt_compiled="golden hour portrait, cinematic",
    )
    assessment = engine.assess(facts)
    assert CRITERION_COMPOSITION in assessment.breakdown.unmeasured


# ---------------------------------------------------------- lighting and color


def test_lighting_and_color_are_measured_from_the_real_file(engine: QualityEngine, tmp_path) -> None:
    path = _image(tmp_path, color=(128, 100, 160))
    facts = MediaFacts(kind=KIND_IMAGE, path=path, width=1280, height=720)
    by = _by_criterion(engine.assess(facts))
    assert by[CRITERION_LIGHTING].source == SOURCE_MEASURED
    assert by[CRITERION_COLOR].source == SOURCE_MEASURED


def test_a_pure_black_frame_fails_lighting(engine: QualityEngine, tmp_path) -> None:
    dark = _image(tmp_path, color=(0, 0, 0))
    facts = MediaFacts(kind=KIND_IMAGE, path=dark, width=1280, height=720)
    lighting = _by_criterion(engine.assess(facts))[CRITERION_LIGHTING]
    assert lighting.score == 0.0  # exposure 0 at black, contrast 0 when flat


def test_a_well_exposed_frame_beats_a_blown_out_one(engine: QualityEngine, tmp_path) -> None:
    good = tmp_path / "good.png"
    checker = Image.new("RGB", (200, 200), (0, 0, 0))
    for x in range(100):
        for y in range(200):
            checker.putpixel((x, y), (200, 200, 200))
    checker.save(good, "PNG")  # mid luminance, strong contrast
    blown = _image(tmp_path, color=(255, 255, 255))
    good_score = _by_criterion(
        engine.assess(MediaFacts(kind=KIND_IMAGE, path=str(good), width=200, height=200))
    )[CRITERION_LIGHTING].score
    blown_score = _by_criterion(
        engine.assess(MediaFacts(kind=KIND_IMAGE, path=blown, width=1280, height=720))
    )[CRITERION_LIGHTING].score
    assert good_score > blown_score


def test_a_grey_frame_scores_low_on_color(engine: QualityEngine, tmp_path) -> None:
    grey = _image(tmp_path, color=(128, 128, 128))  # saturation 0
    saturated = _image(tmp_path.joinpath("s").parent, color=(200, 40, 40))
    grey_facts = MediaFacts(kind=KIND_IMAGE, path=grey, width=1280, height=720)
    grey_score = _by_criterion(engine.assess(grey_facts))[CRITERION_COLOR].score
    assert grey_score < 100.0
    sat = tmp_path / "sat.png"
    Image.new("RGB", (400, 400), (200, 60, 60)).save(sat, "PNG")
    sat_facts = MediaFacts(kind=KIND_IMAGE, path=str(sat), width=400, height=400)
    assert _by_criterion(engine.assess(sat_facts))[CRITERION_COLOR].score > grey_score


def test_a_missing_or_unreadable_file_reads_as_unmeasured_not_scored(engine: QualityEngine, tmp_path) -> None:
    fake = tmp_path / "not-an-image.png"
    fake.write_bytes(b"this is not a png")
    facts = MediaFacts(kind=KIND_IMAGE, path=str(fake), width=1280, height=720)
    assessment = engine.assess(facts)
    assert CRITERION_LIGHTING in assessment.breakdown.unmeasured
    assert CRITERION_COLOR in assessment.breakdown.unmeasured


def test_videos_are_not_pixel_probed(engine: QualityEngine, tmp_path) -> None:
    path = _image(tmp_path)  # a real image at a video path proves the guard is on kind
    facts = MediaFacts(kind=KIND_VIDEO, path=path, width=1280, height=720, fps=24)
    assessment = engine.assess(facts)
    assert CRITERION_LIGHTING in assessment.breakdown.unmeasured
    assert CRITERION_COLOR in assessment.breakdown.unmeasured


# --------------------------------------------------------------------- motion


def test_motion_full_marks_at_the_requested_rate_and_duration(engine: QualityEngine) -> None:
    facts = MediaFacts(
        kind=KIND_VIDEO,
        width=1920,
        height=1080,
        duration_seconds=15.0,
        fps=24,
        requested_duration=15.0,
        requested_fps=24,
    )
    motion = _by_criterion(engine.assess(facts))[CRITERION_MOTION]
    assert motion.score == 100.0


def test_a_slideshow_frame_rate_scores_low(engine: QualityEngine) -> None:
    facts = MediaFacts(kind=KIND_VIDEO, fps=6, requested_fps=24)
    motion = _by_criterion(engine.assess(facts))[CRITERION_MOTION]
    assert motion.score == 25.0


def test_the_default_target_is_the_delivery_grade_24fps(engine: QualityEngine) -> None:
    facts = MediaFacts(kind=KIND_VIDEO, fps=MOTION_FULL_FPS)
    assert _by_criterion(engine.assess(facts))[CRITERION_MOTION].score == 100.0


def test_a_truncated_render_is_punished_beyond_the_tolerance(engine: QualityEngine) -> None:
    exact = MediaFacts(kind=KIND_VIDEO, duration_seconds=15.0, requested_duration=15.0, fps=24, requested_fps=24)
    short = MediaFacts(kind=KIND_VIDEO, duration_seconds=9.0, requested_duration=15.0, fps=24, requested_fps=24)
    assert (
        _by_criterion(engine.assess(short))[CRITERION_MOTION].score
        < _by_criterion(engine.assess(exact))[CRITERION_MOTION].score
    )


def test_a_second_of_duration_drift_is_forgiven(engine: QualityEngine) -> None:
    facts = MediaFacts(kind=KIND_VIDEO, duration_seconds=14.2, requested_duration=15.0, fps=24, requested_fps=24)
    assert _by_criterion(engine.assess(facts))[CRITERION_MOTION].score == 100.0


def test_motion_stays_unmeasured_when_nothing_was_reported(engine: QualityEngine) -> None:
    facts = MediaFacts(kind=KIND_VIDEO, width=1920, height=1080)
    assert CRITERION_MOTION in engine.assess(facts).breakdown.unmeasured


# ------------------------------------------------------------- prompt fidelity


def test_full_retention_scores_100(engine: QualityEngine) -> None:
    facts = MediaFacts(
        kind=KIND_IMAGE,
        width=1024,
        height=1024,
        prompt_original="cinematic portrait golden hour",
        prompt_compiled="ultra realistic cinematic portrait during golden hour",
    )
    fidelity = _by_criterion(engine.assess(facts))[CRITERION_PROMPT_FIDELITY]
    assert fidelity.score == 100.0
    assert fidelity.source == SOURCE_MEASURED


def test_a_compilation_that_dropped_the_subject_scores_lower(engine: QualityEngine) -> None:
    kept = MediaFacts(
        kind=KIND_IMAGE, width=1024, height=1024,
        prompt_original="red truck desert sunset",
        prompt_compiled="red truck in the desert at sunset, cinematic",
    )
    dropped = MediaFacts(
        kind=KIND_IMAGE, width=1024, height=1024,
        prompt_original="red truck desert sunset",
        prompt_compiled="a generic landscape, cinematic",
    )
    assert (
        _by_criterion(engine.assess(dropped))[CRITERION_PROMPT_FIDELITY].score
        < _by_criterion(engine.assess(kept))[CRITERION_PROMPT_FIDELITY].score
    )


def test_short_stopwords_are_ignored(engine: QualityEngine) -> None:
    facts = MediaFacts(
        kind=KIND_IMAGE, width=1024, height=1024,
        prompt_original="a of it cinematic truck",
        prompt_compiled="cinematic truck",
    )
    # "a", "of", "it" are all under the significance threshold.
    assert all(len(t) < FIDELITY_MIN_TOKEN_LENGTH for t in ("a", "of", "it"))
    assert _by_criterion(engine.assess(facts))[CRITERION_PROMPT_FIDELITY].score == 100.0


def test_fidelity_stays_unmeasured_without_both_prompts(engine: QualityEngine) -> None:
    facts = MediaFacts(kind=KIND_IMAGE, width=1024, height=1024, prompt_original="truck")
    assert CRITERION_PROMPT_FIDELITY in engine.assess(facts).breakdown.unmeasured


# ---------------------------------------------------------- detector override


def test_face_hands_eyes_only_exist_through_a_detector(engine: QualityEngine) -> None:
    facts = MediaFacts(kind=KIND_IMAGE, width=1024, height=1024)
    assessment = engine.assess(facts)
    for criterion in (CRITERION_FACE, CRITERION_HANDS, CRITERION_EYES):
        assert criterion in assessment.breakdown.unmeasured


def test_a_detector_signal_wins_over_the_engines_own_heuristic(engine: QualityEngine) -> None:
    facts = MediaFacts(kind=KIND_IMAGE, width=1920, height=1080, aspect_ratio_expected=16 / 9)
    assessment = engine.assess(facts, signals={CRITERION_COMPOSITION: 12.0})
    composition = _by_criterion(assessment)[CRITERION_COMPOSITION]
    assert composition.score == 12.0
    assert composition.source == SOURCE_DETECTOR


# -------------------------------------------------------------- report shape


def test_the_report_carries_everything_etapa_3_names(engine: QualityEngine, tmp_path) -> None:
    path = _image(tmp_path, size=(640, 360))
    facts = MediaFacts(
        kind=KIND_IMAGE,
        path=path,
        width=640,
        height=360,
        aspect_ratio_expected=16 / 9,
        prompt_original="cinematic truck",
        prompt_compiled="cinematic truck, ultra detailed",
    )
    assessment = engine.assess(facts, signals={CRITERION_FACE: 96.0, CRITERION_HANDS: 95.0, CRITERION_EYES: 95.0})
    document = assessment.to_dict()
    for key in (
        "overall_score", "status", "issues", "strengths", "suggestions",
        "retry_recommended", "upscale_recommended", "criteria", "unmeasured",
        "engine_version", "facts",
    ):
        assert key in document
    assert document["engine_version"] == QUALITY_ENGINE_VERSION
    assert 0 <= document["overall_score"] <= 100
    assert document["facts"]["short_side"] == 360
    assert document["facts"]["detector_criteria"] == sorted([CRITERION_FACE, CRITERION_HANDS, CRITERION_EYES])


def test_a_bad_render_is_recommended_for_retry_never_retried(engine: QualityEngine) -> None:
    facts = MediaFacts(kind=KIND_IMAGE, width=1080, height=1080, aspect_ratio_expected=16 / 9)
    assessment = engine.assess(
        facts, signals={CRITERION_FACE: 10.0, CRITERION_HANDS: 5.0, CRITERION_EYES: 10.0}
    )
    assert assessment.status == STATUS_RETRY
    assert assessment.retry_recommended
    assert not assessment.upscale_recommended
    assert assessment.issues  # the report says why
    assert assessment.suggestions  # and what to do about it


def test_an_approved_small_render_carries_the_upscale_recommendation(engine: QualityEngine) -> None:
    facts = MediaFacts(kind=KIND_IMAGE, width=960, height=540, aspect_ratio_expected=16 / 9)
    assessment = engine.assess(
        facts, signals={CRITERION_FACE: 98.0, CRITERION_HANDS: 97.0, CRITERION_EYES: 98.0}
    )
    assert assessment.overall_score >= 85
    assert assessment.upscale_recommended


def test_a_custom_scorer_rebalances_the_engine(tmp_path) -> None:
    heavy_face = QualityEngine(QualityScorer(weights={CRITERION_FACE: 1000.0}))
    facts = MediaFacts(kind=KIND_IMAGE, width=1920, height=1080, aspect_ratio_expected=16 / 9)
    weighted = heavy_face.assess(facts, signals={CRITERION_FACE: 0.0})
    balanced = QualityEngine().assess(facts, signals={CRITERION_FACE: 0.0})
    assert weighted.overall_score < balanced.overall_score


# ------------------------------------------------------------ geometry probing


def test_the_engine_probes_the_real_files_geometry(engine: QualityEngine, tmp_path) -> None:
    path = _image(tmp_path, size=(800, 450))
    facts = engine.with_probed_geometry(MediaFacts(kind=KIND_IMAGE, path=path))
    assert (facts.width, facts.height) == (800, 450)


def test_probing_never_overrides_reported_geometry(engine: QualityEngine, tmp_path) -> None:
    path = _image(tmp_path, size=(800, 450))
    facts = engine.with_probed_geometry(MediaFacts(kind=KIND_IMAGE, path=path, width=1920, height=1080))
    assert (facts.width, facts.height) == (1920, 1080)


def test_probing_skips_videos_and_unreadable_files(engine: QualityEngine, tmp_path) -> None:
    video = MediaFacts(kind=KIND_VIDEO, path=str(tmp_path / "clip.mp4"))
    assert engine.with_probed_geometry(video) is video
    broken = tmp_path / "broken.png"
    broken.write_bytes(b"not a png")
    facts = MediaFacts(kind=KIND_IMAGE, path=str(broken))
    assert engine.with_probed_geometry(facts).width == 0


def test_probing_without_a_path_is_a_no_op(engine: QualityEngine) -> None:
    facts = MediaFacts(kind=KIND_IMAGE)
    assert engine.with_probed_geometry(facts) is facts


# --------------------------------------------------------- defensive branches


def test_the_band_helper_floors_when_the_band_touches_the_ceiling() -> None:
    """A band whose high edge is the ceiling has no falloff room above it —
    the helper must floor instead of dividing by zero."""

    from app.quality.quality_engine import _band_score

    assert _band_score(260.0, 60.0, 255.0, 255.0) == 0.0


def test_the_motion_probe_refuses_a_non_video_by_contract(engine: QualityEngine) -> None:
    """The public path never routes an image here (motion is video-only in
    the scorer), but the guard is the method's own contract."""

    assert engine._measure_motion(MediaFacts(kind=KIND_IMAGE, fps=24)) is None
