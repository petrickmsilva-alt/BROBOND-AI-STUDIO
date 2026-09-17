"""V3.4 — Quality Score: weighted 0–100 aggregation over eight criteria.

The score is a weighted mean of per-criterion measurements, each on the same
0–100 scale. Eight criteria exist (SPRINT V3.4 ETAPA 2): Face, Hands, Eyes,
Composition, Lighting, Color, Motion and Prompt Fidelity. Motion applies to
video only — an image is never judged on movement it cannot have.

Two rules govern everything here:

* **No magic numbers.** Every weight, bound and rounding decision is a named
  constant at module level, and the weights are constructor-injectable so a
  deployment can re-balance them without touching this file.
* **Unmeasured is not zero.** A criterion nothing measured is *excluded* from
  the weighted mean and reported in ``unmeasured`` — averaging in an invented
  0 (or an invented 100) would be exactly the failure mode ``SYSTEM_PROMPT.md``
  forbids ("Não invente… outputs inexistentes"). The weights are therefore
  relative: the denominator is the weight sum of what was actually measured.

Independence: pure data in, pure data out. No framework, no database, no
sibling imports — the same layering rule ``campaign/brief_interpreter.py``
and ``continuity/*_lock.py`` follow.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence


class QualityValidationError(Exception):
    """Raised when an input to the scorer or engine is not usable."""


# --------------------------------------------------------------------- criteria

CRITERION_FACE = "face"
CRITERION_HANDS = "hands"
CRITERION_EYES = "eyes"
CRITERION_COMPOSITION = "composition"
CRITERION_LIGHTING = "lighting"
CRITERION_COLOR = "color"
CRITERION_MOTION = "motion"
CRITERION_PROMPT_FIDELITY = "prompt_fidelity"

#: Canonical order — reports, radars and docs all present criteria this way.
CRITERIA: tuple[str, ...] = (
    CRITERION_FACE,
    CRITERION_HANDS,
    CRITERION_EYES,
    CRITERION_COMPOSITION,
    CRITERION_LIGHTING,
    CRITERION_COLOR,
    CRITERION_MOTION,
    CRITERION_PROMPT_FIDELITY,
)

#: What each media kind can be judged on. Motion is video-only.
IMAGE_CRITERIA: tuple[str, ...] = tuple(c for c in CRITERIA if c != CRITERION_MOTION)
VIDEO_CRITERIA: tuple[str, ...] = CRITERIA

KIND_IMAGE = "image"
KIND_VIDEO = "video"
KINDS: tuple[str, ...] = (KIND_IMAGE, KIND_VIDEO)

# ---------------------------------------------------------------------- weights

#: Default relative weights (SPRINT V3.4: "Cada critério possui peso
#: configurável"). They are *relative*, not percentages: the aggregation
#: normalises by the weight sum of the measured criteria, so the same table
#: serves images (7 criteria) and videos (8) without a second copy.
WEIGHT_FACE = 20.0
WEIGHT_HANDS = 15.0
WEIGHT_EYES = 15.0
WEIGHT_COMPOSITION = 15.0
WEIGHT_LIGHTING = 10.0
WEIGHT_COLOR = 10.0
WEIGHT_MOTION = 10.0
WEIGHT_PROMPT_FIDELITY = 15.0

DEFAULT_WEIGHTS: dict[str, float] = {
    CRITERION_FACE: WEIGHT_FACE,
    CRITERION_HANDS: WEIGHT_HANDS,
    CRITERION_EYES: WEIGHT_EYES,
    CRITERION_COMPOSITION: WEIGHT_COMPOSITION,
    CRITERION_LIGHTING: WEIGHT_LIGHTING,
    CRITERION_COLOR: WEIGHT_COLOR,
    CRITERION_MOTION: WEIGHT_MOTION,
    CRITERION_PROMPT_FIDELITY: WEIGHT_PROMPT_FIDELITY,
}

#: Bounds of every score in the system — criterion measurements and the
#: aggregated result alike.
SCORE_FLOOR = 0.0
SCORE_CEILING = 100.0

#: The overall score is delivered as an integer 0–100 (SPRINT V3.4 Definition
#: of Done: "Score 0–100"); per-criterion scores keep one decimal so a radar
#: chart does not lie about ties.
CRITERION_ROUND_DIGITS = 1


def clamp_score(value: float) -> float:
    """Pin a raw heuristic result into the 0–100 contract."""

    return max(SCORE_FLOOR, min(SCORE_CEILING, float(value)))


@dataclass(frozen=True)
class CriterionScore:
    """One measured criterion: the score, where it came from, and why."""

    criterion: str
    score: float
    weight: float
    source: str
    detail: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "criterion": self.criterion,
            "score": round(self.score, CRITERION_ROUND_DIGITS),
            "weight": self.weight,
            "source": self.source,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class ScoreBreakdown:
    """The aggregation result: the overall score and everything behind it."""

    overall: int
    criteria: tuple[CriterionScore, ...]
    unmeasured: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "overall": self.overall,
            "criteria": [c.to_dict() for c in self.criteria],
            "unmeasured": list(self.unmeasured),
        }


class QualityScorer:
    """Weighted aggregation. Deterministic; owns no thresholds and no rules."""

    def __init__(self, weights: Mapping[str, float] | None = None) -> None:
        table = dict(DEFAULT_WEIGHTS)
        if weights is not None:
            for criterion, weight in weights.items():
                if criterion not in CRITERIA:
                    raise QualityValidationError(f"unknown criterion {criterion!r}")
                if not isinstance(weight, (int, float)) or isinstance(weight, bool):
                    raise QualityValidationError(f"weight for {criterion!r} must be a number")
                if float(weight) <= 0:
                    raise QualityValidationError(f"weight for {criterion!r} must be positive")
                table[criterion] = float(weight)
        self.weights: dict[str, float] = table

    # ------------------------------------------------------------------ public

    def applicable(self, kind: str) -> tuple[str, ...]:
        """Which criteria a media kind can be judged on."""

        if kind == KIND_IMAGE:
            return IMAGE_CRITERIA
        if kind == KIND_VIDEO:
            return VIDEO_CRITERIA
        raise QualityValidationError(f"unknown media kind {kind!r}")

    def weight_of(self, criterion: str) -> float:
        if criterion not in CRITERIA:
            raise QualityValidationError(f"unknown criterion {criterion!r}")
        return self.weights[criterion]

    def aggregate(self, kind: str, measurements: Sequence[CriterionScore]) -> ScoreBreakdown:
        """Weighted mean of the measured criteria; the rest listed, not guessed.

        Raises when a measurement is out of range, duplicated, inapplicable to
        the kind, or when nothing was measured at all — "we learned nothing"
        must never read as a score.
        """

        applicable = self.applicable(kind)
        seen: set[str] = set()
        for measurement in measurements:
            if measurement.criterion not in applicable:
                raise QualityValidationError(
                    f"criterion {measurement.criterion!r} does not apply to {kind!r}"
                )
            if measurement.criterion in seen:
                raise QualityValidationError(f"criterion {measurement.criterion!r} measured twice")
            if not SCORE_FLOOR <= measurement.score <= SCORE_CEILING:
                raise QualityValidationError(
                    f"{measurement.criterion} score {measurement.score} is outside "
                    f"{SCORE_FLOOR:.0f}–{SCORE_CEILING:.0f}"
                )
            seen.add(measurement.criterion)
        if not seen:
            raise QualityValidationError("no criterion could be measured")

        total_weight = sum(m.weight for m in measurements)
        weighted = sum(m.score * m.weight for m in measurements)
        overall = int(round(clamp_score(weighted / total_weight)))
        ordered = tuple(sorted(measurements, key=lambda m: CRITERIA.index(m.criterion)))
        unmeasured = tuple(c for c in applicable if c not in seen)
        return ScoreBreakdown(overall=overall, criteria=ordered, unmeasured=unmeasured)
