"""V3.4 ETAPA 7 — the weighted 0–100 aggregation (Score).

The properties pinned here are the sprint's contract: eight criteria, every
weight configurable, no magic numbers in the aggregation path, motion only
for video, and — the honesty rule — an unmeasured criterion is excluded and
named, never averaged in as an invented zero.
"""
from __future__ import annotations

import pytest

from app.quality.quality_score import (
    CRITERIA,
    CRITERION_COLOR,
    CRITERION_COMPOSITION,
    CRITERION_EYES,
    CRITERION_FACE,
    CRITERION_HANDS,
    CRITERION_LIGHTING,
    CRITERION_MOTION,
    CRITERION_PROMPT_FIDELITY,
    CriterionScore,
    DEFAULT_WEIGHTS,
    IMAGE_CRITERIA,
    KIND_IMAGE,
    KIND_VIDEO,
    KINDS,
    QualityScorer,
    QualityValidationError,
    SCORE_CEILING,
    SCORE_FLOOR,
    clamp_score,
)


def _m(criterion: str, score: float, weight: float | None = None) -> CriterionScore:
    return CriterionScore(
        criterion=criterion,
        score=score,
        weight=DEFAULT_WEIGHTS[criterion] if weight is None else weight,
        source="detector",
    )


# ------------------------------------------------------------------ vocabulary


def test_the_eight_criteria_of_the_sprint_exist_in_canonical_order() -> None:
    assert CRITERIA == (
        CRITERION_FACE,
        CRITERION_HANDS,
        CRITERION_EYES,
        CRITERION_COMPOSITION,
        CRITERION_LIGHTING,
        CRITERION_COLOR,
        CRITERION_MOTION,
        CRITERION_PROMPT_FIDELITY,
    )


def test_motion_applies_to_video_only() -> None:
    scorer = QualityScorer()
    assert CRITERION_MOTION not in scorer.applicable(KIND_IMAGE)
    assert CRITERION_MOTION in scorer.applicable(KIND_VIDEO)
    assert scorer.applicable(KIND_IMAGE) == IMAGE_CRITERIA


def test_every_criterion_has_a_default_weight_and_all_are_positive() -> None:
    assert set(DEFAULT_WEIGHTS) == set(CRITERIA)
    assert all(weight > 0 for weight in DEFAULT_WEIGHTS.values())


def test_an_unknown_media_kind_is_refused() -> None:
    with pytest.raises(QualityValidationError):
        QualityScorer().applicable("audio")


def test_the_kind_vocabulary_is_image_and_video() -> None:
    assert KINDS == (KIND_IMAGE, KIND_VIDEO)


# -------------------------------------------------------------------- clamping


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(-5.0, SCORE_FLOOR), (0.0, 0.0), (55.5, 55.5), (100.0, 100.0), (140.0, SCORE_CEILING)],
)
def test_clamp_score_pins_into_the_contract(raw: float, expected: float) -> None:
    assert clamp_score(raw) == expected


# ----------------------------------------------------------------- aggregation


def test_a_perfect_measurement_set_scores_100() -> None:
    scorer = QualityScorer()
    measurements = [_m(c, 100.0) for c in scorer.applicable(KIND_VIDEO)]
    breakdown = scorer.aggregate(KIND_VIDEO, measurements)
    assert breakdown.overall == 100
    assert breakdown.unmeasured == ()


def test_a_worthless_measurement_set_scores_0() -> None:
    scorer = QualityScorer()
    measurements = [_m(c, 0.0) for c in scorer.applicable(KIND_IMAGE)]
    assert scorer.aggregate(KIND_IMAGE, measurements).overall == 0


def test_the_aggregate_is_the_weighted_mean_not_the_plain_mean() -> None:
    scorer = QualityScorer(weights={CRITERION_FACE: 90.0, CRITERION_HANDS: 10.0})
    breakdown = scorer.aggregate(
        KIND_IMAGE,
        [_m(CRITERION_FACE, 100.0, 90.0), _m(CRITERION_HANDS, 0.0, 10.0)],
    )
    # Plain mean would be 50; the 90/10 weighting pulls it to 90.
    assert breakdown.overall == 90


def test_weights_are_configurable_per_scorer() -> None:
    default = QualityScorer()
    rebalanced = QualityScorer(weights={CRITERION_COLOR: 80.0})
    assert default.weight_of(CRITERION_COLOR) == DEFAULT_WEIGHTS[CRITERION_COLOR]
    assert rebalanced.weight_of(CRITERION_COLOR) == 80.0
    # The other weights are untouched by a partial table.
    assert rebalanced.weight_of(CRITERION_FACE) == DEFAULT_WEIGHTS[CRITERION_FACE]


def test_the_constructor_never_mutates_the_default_table() -> None:
    before = dict(DEFAULT_WEIGHTS)
    QualityScorer(weights={CRITERION_LIGHTING: 42.0})
    assert DEFAULT_WEIGHTS == before


def test_an_unmeasured_criterion_is_excluded_and_named_not_zeroed() -> None:
    scorer = QualityScorer()
    breakdown = scorer.aggregate(
        KIND_IMAGE,
        [_m(CRITERION_FACE, 80.0), _m(CRITERION_COMPOSITION, 80.0)],
    )
    # If the six missing criteria were averaged in as zeros the overall would
    # collapse; excluding them keeps it at the measured mean.
    assert breakdown.overall == 80
    assert CRITERION_HANDS in breakdown.unmeasured
    assert CRITERION_EYES in breakdown.unmeasured
    assert CRITERION_MOTION not in breakdown.unmeasured  # video-only, not applicable


def test_criteria_come_back_in_canonical_order_regardless_of_input_order() -> None:
    scorer = QualityScorer()
    breakdown = scorer.aggregate(
        KIND_IMAGE,
        [_m(CRITERION_PROMPT_FIDELITY, 70.0), _m(CRITERION_FACE, 70.0), _m(CRITERION_LIGHTING, 70.0)],
    )
    assert [c.criterion for c in breakdown.criteria] == [
        CRITERION_FACE,
        CRITERION_LIGHTING,
        CRITERION_PROMPT_FIDELITY,
    ]


def test_the_breakdown_serialises_completely() -> None:
    scorer = QualityScorer()
    document = scorer.aggregate(KIND_IMAGE, [_m(CRITERION_FACE, 77.75)]).to_dict()
    assert document["overall"] == 78
    assert document["criteria"][0]["criterion"] == CRITERION_FACE
    assert document["criteria"][0]["score"] == 77.8  # one decimal, no lie about ties
    assert CRITERION_COLOR in document["unmeasured"]


# ------------------------------------------------------------------ validation


def test_measuring_nothing_is_an_error_not_a_score() -> None:
    with pytest.raises(QualityValidationError, match="no criterion"):
        QualityScorer().aggregate(KIND_IMAGE, [])


def test_a_score_above_the_ceiling_is_refused() -> None:
    with pytest.raises(QualityValidationError, match="outside"):
        QualityScorer().aggregate(KIND_IMAGE, [_m(CRITERION_FACE, 101.0)])


def test_a_negative_score_is_refused() -> None:
    with pytest.raises(QualityValidationError, match="outside"):
        QualityScorer().aggregate(KIND_IMAGE, [_m(CRITERION_FACE, -1.0)])


def test_a_duplicated_criterion_is_refused() -> None:
    with pytest.raises(QualityValidationError, match="twice"):
        QualityScorer().aggregate(KIND_IMAGE, [_m(CRITERION_FACE, 50.0), _m(CRITERION_FACE, 60.0)])


def test_motion_on_an_image_is_refused() -> None:
    with pytest.raises(QualityValidationError, match="does not apply"):
        QualityScorer().aggregate(KIND_IMAGE, [_m(CRITERION_MOTION, 50.0)])


def test_an_unknown_weight_key_is_refused() -> None:
    with pytest.raises(QualityValidationError, match="unknown criterion"):
        QualityScorer(weights={"vibe": 10.0})


def test_a_zero_or_negative_weight_is_refused() -> None:
    with pytest.raises(QualityValidationError, match="positive"):
        QualityScorer(weights={CRITERION_FACE: 0.0})
    with pytest.raises(QualityValidationError, match="positive"):
        QualityScorer(weights={CRITERION_FACE: -3.0})


def test_a_non_numeric_weight_is_refused() -> None:
    with pytest.raises(QualityValidationError, match="number"):
        QualityScorer(weights={CRITERION_FACE: "heavy"})  # type: ignore[dict-item]
    with pytest.raises(QualityValidationError, match="number"):
        QualityScorer(weights={CRITERION_FACE: True})  # type: ignore[dict-item]


def test_weight_of_refuses_an_unknown_criterion() -> None:
    with pytest.raises(QualityValidationError, match="unknown criterion"):
        QualityScorer().weight_of("vibe")
