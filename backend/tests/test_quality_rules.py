"""V3.4 ETAPA 7 — the decision bands and findings (Rules + Decision).

ETAPA 4's contract verbatim: < 70 retry, 70–84 manual review, 85+ approved,
95+ masterpiece — and the engine only recommends. The upscale rule and the
issue/strength/suggestion prose are pinned here too, because they are the
other two things `quality_rules` owns.
"""
from __future__ import annotations

import pytest

from app.quality.quality_rules import (
    APPROVED_AT,
    ISSUE_BELOW,
    ISSUE_TEXT,
    MASTERPIECE_AT,
    QUALITY_STATUSES,
    QualityDecision,
    RETRY_BELOW,
    STATUS_APPROVED,
    STATUS_MANUAL_REVIEW,
    STATUS_MASTERPIECE,
    STATUS_RETRY,
    STRENGTH_AT,
    STRENGTH_TEXT,
    SUGGESTION_TEXT,
    UPSCALE_SHORT_SIDE_BELOW,
    build_findings,
    decide,
    status_for,
)
from app.quality.quality_score import (
    CRITERIA,
    CRITERION_COMPOSITION,
    CRITERION_FACE,
    CRITERION_HANDS,
    CriterionScore,
    DEFAULT_WEIGHTS,
    KIND_IMAGE,
    QualityScorer,
    QualityValidationError,
)


def _breakdown(*pairs: tuple[str, float]):
    scorer = QualityScorer()
    return scorer.aggregate(
        KIND_IMAGE,
        [
            CriterionScore(criterion=c, score=s, weight=DEFAULT_WEIGHTS[c], source="detector")
            for c, s in pairs
        ],
    )


# ---------------------------------------------------------------------- bands


def test_the_sprint_boundaries_are_the_documented_ones() -> None:
    assert (RETRY_BELOW, APPROVED_AT, MASTERPIECE_AT) == (70, 85, 95)


@pytest.mark.parametrize(
    ("score", "status"),
    [
        (0, STATUS_RETRY),
        (69, STATUS_RETRY),
        (70, STATUS_MANUAL_REVIEW),
        (84, STATUS_MANUAL_REVIEW),
        (85, STATUS_APPROVED),
        (94, STATUS_APPROVED),
        (95, STATUS_MASTERPIECE),
        (100, STATUS_MASTERPIECE),
    ],
)
def test_every_band_boundary(score: int, status: str) -> None:
    assert status_for(score) == status


def test_statuses_are_ordered_worst_to_best() -> None:
    assert QUALITY_STATUSES == (
        STATUS_RETRY,
        STATUS_MANUAL_REVIEW,
        STATUS_APPROVED,
        STATUS_MASTERPIECE,
    )


@pytest.mark.parametrize("score", [-1, 101])
def test_an_out_of_range_score_is_refused(score: int) -> None:
    with pytest.raises(QualityValidationError, match="outside"):
        status_for(score)


# ------------------------------------------------------------------- decision


def test_below_70_recommends_retry_and_never_upscale() -> None:
    decision = decide(69, short_side_pixels=512)
    assert decision == QualityDecision(
        status=STATUS_RETRY, retry_recommended=True, upscale_recommended=False
    )


def test_manual_review_recommends_neither() -> None:
    decision = decide(75, short_side_pixels=512)
    assert decision.status == STATUS_MANUAL_REVIEW
    assert not decision.retry_recommended
    assert not decision.upscale_recommended


def test_an_approved_small_render_earns_the_upscale_recommendation() -> None:
    decision = decide(88, short_side_pixels=UPSCALE_SHORT_SIDE_BELOW - 1)
    assert decision.status == STATUS_APPROVED
    assert decision.upscale_recommended
    assert not decision.retry_recommended


def test_an_approved_large_render_needs_no_upscale() -> None:
    assert not decide(88, short_side_pixels=UPSCALE_SHORT_SIDE_BELOW).upscale_recommended


def test_a_masterpiece_can_still_be_small_enough_to_upscale() -> None:
    decision = decide(97, short_side_pixels=720)
    assert decision.status == STATUS_MASTERPIECE
    assert decision.upscale_recommended


def test_unknown_geometry_never_earns_an_upscale() -> None:
    # 0 means nobody measured the pixels — recommending an upscale for them
    # would be inventing a fact.
    assert not decide(90, short_side_pixels=0).upscale_recommended


def test_the_decision_is_a_recommendation_object_not_an_action() -> None:
    document = decide(50).to_dict()
    assert document == {
        "status": STATUS_RETRY,
        "retry_recommended": True,
        "upscale_recommended": False,
    }


# ------------------------------------------------------------------- findings


def test_a_weak_criterion_becomes_an_issue_with_a_suggestion() -> None:
    issues, strengths, suggestions = build_findings(
        _breakdown((CRITERION_HANDS, ISSUE_BELOW - 1), (CRITERION_FACE, 70.0))
    )
    assert issues == [ISSUE_TEXT[CRITERION_HANDS]]
    assert suggestions == [SUGGESTION_TEXT[CRITERION_HANDS]]
    assert strengths == []


def test_a_strong_criterion_becomes_a_strength() -> None:
    issues, strengths, suggestions = build_findings(
        _breakdown((CRITERION_FACE, STRENGTH_AT), (CRITERION_HANDS, 70.0))
    )
    assert strengths == [STRENGTH_TEXT[CRITERION_FACE]]
    assert issues == []
    assert suggestions == []


def test_the_middle_band_produces_no_finding_at_all() -> None:
    issues, strengths, suggestions = build_findings(
        _breakdown((CRITERION_FACE, ISSUE_BELOW), (CRITERION_HANDS, STRENGTH_AT - 0.1))
    )
    assert (issues, strengths, suggestions) == ([], [], [])


def test_every_issue_always_travels_with_its_suggestion() -> None:
    issues, _, suggestions = build_findings(
        _breakdown((CRITERION_FACE, 10.0), (CRITERION_HANDS, 20.0), (CRITERION_COMPOSITION, 30.0))
    )
    assert len(issues) == len(suggestions) == 3


def test_every_criterion_has_prose_for_all_three_tables() -> None:
    for criterion in CRITERIA:
        assert criterion in ISSUE_TEXT
        assert criterion in STRENGTH_TEXT
        assert criterion in SUGGESTION_TEXT
        assert ISSUE_TEXT[criterion] and STRENGTH_TEXT[criterion] and SUGGESTION_TEXT[criterion]
