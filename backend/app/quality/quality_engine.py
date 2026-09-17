"""V3.4 — Quality Engine: turns facts about a render into a scored report.

The honesty rule this repository lives by (``SYSTEM_PROMPT.md``: "Não invente
arquivos, jobs concluídos, modelos carregados ou outputs inexistentes")
shapes the whole engine. ``core/quality.py`` (ETAPA 14) refuses to produce an
aesthetic number because the gate cannot see the image — this engine keeps
that promise while still delivering the sprint's 0–100 score, by being
explicit about **where every criterion's number comes from**:

* **measured** — computed here from the artifact and the spec: composition
  (geometry against the requested aspect ratio and the resolution target),
  lighting and color (pixel statistics read from the real file via Pillow),
  motion (frame rate and duration against the spec), prompt fidelity (token
  retention between the original and the compiled prompt);
* **detector** — supplied by the caller from an external detector run (face,
  hands, eyes confidences — or overrides for any criterion a better probe
  measured). The engine never fabricates these;
* **unmeasured** — everything else. An unmeasured criterion is *excluded*
  from the weighted mean and listed by name, never averaged in as an
  invented number.

The engine also never acts. It recommends (retry / manual review / approve /
masterpiece, plus upscale when a good render is small) and the caller — a
human at ``/studio/quality`` — decides.

Independence: composes its two siblings (``quality_score``,
``quality_rules``) and imports nothing else but the standard library and,
lazily and optionally, Pillow.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Mapping

from .quality_rules import QualityDecision, build_findings, decide
from .quality_score import (
    CRITERIA,
    CRITERION_COLOR,
    CRITERION_COMPOSITION,
    CRITERION_LIGHTING,
    CRITERION_MOTION,
    CRITERION_PROMPT_FIDELITY,
    CriterionScore,
    KIND_IMAGE,
    KIND_VIDEO,
    KINDS,
    QualityScorer,
    QualityValidationError,
    SCORE_CEILING,
    SCORE_FLOOR,
    ScoreBreakdown,
    clamp_score,
)

#: Version stamp persisted with every report (ETAPA 6: ``quality_version``).
#: Bump when a heuristic, weight default or band changes, so an old report is
#: never mistaken for the current engine's opinion.
QUALITY_ENGINE_VERSION = 1

#: Where a criterion's number came from.
SOURCE_MEASURED = "measured"
SOURCE_DETECTOR = "detector"
SOURCES: tuple[str, ...] = (SOURCE_MEASURED, SOURCE_DETECTOR)

# ------------------------------------------------------- composition constants

#: Relative aspect-ratio deviation fully forgiven (the rounding a pipeline
#: does on its way to a multiple of eight) — same figure the structural gate
#: tolerates.
ASPECT_DEVIATION_FORGIVEN = 0.03

#: Relative deviation at which the composition score reaches zero: a 1:1
#: render against a 16:9 request deviates ~0.44 and lands well past this.
ASPECT_DEVIATION_ZERO = 0.25

#: Short side (pixels) at which the resolution component earns full marks.
RESOLUTION_TARGET_PIXELS = 1024

#: Short side below which the render is structurally broken (gate's floor).
RESOLUTION_FLOOR_PIXELS = 64

# ---------------------------------------------------------- lighting constants

#: Mean-luminance band (0–255) considered well exposed. Outside it the score
#: falls linearly to zero at pure black / pure white.
LUMINANCE_LOW = 60.0
LUMINANCE_HIGH = 200.0
LUMINANCE_MAX = 255.0

#: Luminance standard deviation at which contrast earns full marks. A flat
#: frame (stddev 0) earns zero on this component.
CONTRAST_TARGET_STDDEV = 50.0

# ------------------------------------------------------------- color constants

#: Mean-saturation band (0–255 in HSV) considered a deliberate palette.
#: Below the band reads as washed out, above it as clipped neon.
SATURATION_LOW = 40.0
SATURATION_HIGH = 200.0
SATURATION_MAX = 255.0

# ------------------------------------------------------------ motion constants

#: Frame rate at which delivery-grade motion earns full marks when the spec
#: did not name one.
MOTION_FULL_FPS = 24

#: Seconds of duration deviation fully forgiven, matching the gate.
DURATION_TOLERANCE_SECONDS = 1.0

#: Relative duration deviation at which the motion component reaches zero.
DURATION_DEVIATION_ZERO = 0.5

# ---------------------------------------------------- prompt fidelity constants

#: Tokens shorter than this carry no meaning worth checking ("a", "of", "de").
FIDELITY_MIN_TOKEN_LENGTH = 3


def _band_score(value: float, low: float, high: float, ceiling: float) -> float:
    """100 inside [low, high]; linear falloff to 0 at the extremes."""

    if low <= value <= high:
        return SCORE_CEILING
    if value < low:
        return clamp_score(SCORE_CEILING * value / low) if low > 0 else SCORE_FLOOR
    span = ceiling - high
    if span <= 0:
        return SCORE_FLOOR
    return clamp_score(SCORE_CEILING * (ceiling - value) / span)


def _falloff(deviation: float, forgiven: float, zero_at: float) -> float:
    """100 up to `forgiven`, then linear to 0 at `zero_at`."""

    if deviation <= forgiven:
        return SCORE_CEILING
    if deviation >= zero_at:
        return SCORE_FLOOR
    return clamp_score(SCORE_CEILING * (zero_at - deviation) / (zero_at - forgiven))


@dataclass(frozen=True)
class MediaFacts:
    """What is actually known about one rendered asset and the spec behind it.

    Zero means "not reported", the same convention as ``MeasuredOutput`` in
    the structural gate: the engine skips what it cannot know instead of
    guessing.
    """

    kind: str
    path: str = ""
    width: int = 0
    height: int = 0
    duration_seconds: float = 0.0
    fps: int = 0
    aspect_ratio_expected: float = 0.0
    requested_duration: float = 0.0
    requested_fps: int = 0
    prompt_original: str = ""
    prompt_compiled: str = ""

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise QualityValidationError(f"unknown media kind {self.kind!r}")

    @property
    def short_side(self) -> int:
        if self.width > 0 and self.height > 0:
            return min(self.width, self.height)
        return 0


@dataclass(frozen=True)
class QualityAssessment:
    """The engine's full answer for one asset (ETAPA 3's report shape)."""

    kind: str
    overall_score: int
    status: str
    retry_recommended: bool
    upscale_recommended: bool
    issues: tuple[str, ...]
    strengths: tuple[str, ...]
    suggestions: tuple[str, ...]
    breakdown: ScoreBreakdown
    engine_version: int = QUALITY_ENGINE_VERSION
    facts: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "overall_score": self.overall_score,
            "status": self.status,
            "retry_recommended": self.retry_recommended,
            "upscale_recommended": self.upscale_recommended,
            "issues": list(self.issues),
            "strengths": list(self.strengths),
            "suggestions": list(self.suggestions),
            "criteria": [c.to_dict() for c in self.breakdown.criteria],
            "unmeasured": list(self.breakdown.unmeasured),
            "engine_version": self.engine_version,
            "facts": dict(self.facts),
        }


class QualityEngine:
    """Deterministic composition of measurements, weights, bands and prose."""

    def __init__(self, scorer: QualityScorer | None = None) -> None:
        self.scorer = scorer or QualityScorer()

    # ------------------------------------------------------------------ public

    def assess(
        self,
        facts: MediaFacts,
        *,
        signals: Mapping[str, float] | None = None,
    ) -> QualityAssessment:
        """Score one asset from its facts plus optional detector signals.

        ``signals`` maps criterion name → 0–100 confidence from an external
        detector. A signal always wins over the engine's own heuristic for
        the same criterion — the detector saw pixels this process may not
        have.
        """

        detector = self._validated_signals(facts.kind, signals)
        measurements: list[CriterionScore] = []
        for criterion in self.scorer.applicable(facts.kind):
            if criterion in detector:
                measurements.append(
                    CriterionScore(
                        criterion=criterion,
                        score=detector[criterion],
                        weight=self.scorer.weight_of(criterion),
                        source=SOURCE_DETECTOR,
                        detail="confiança reportada por detector externo",
                    )
                )
                continue
            measured = self._measure(criterion, facts)
            if measured is not None:
                measurements.append(measured)

        breakdown = self.scorer.aggregate(facts.kind, measurements)
        decision = decide(breakdown.overall, short_side_pixels=facts.short_side)
        issues, strengths, suggestions = build_findings(breakdown)
        return QualityAssessment(
            kind=facts.kind,
            overall_score=breakdown.overall,
            status=decision.status,
            retry_recommended=decision.retry_recommended,
            upscale_recommended=decision.upscale_recommended,
            issues=tuple(issues),
            strengths=tuple(strengths),
            suggestions=tuple(suggestions),
            breakdown=breakdown,
            facts={
                "path": facts.path,
                "width": facts.width,
                "height": facts.height,
                "short_side": facts.short_side,
                "duration_seconds": facts.duration_seconds,
                "fps": facts.fps,
                "detector_criteria": sorted(detector),
            },
        )

    def with_probed_geometry(self, facts: MediaFacts) -> MediaFacts:
        """Read the real image's dimensions when the caller did not send them.

        Kept in the engine so the HTTP layer never measures anything itself.
        Videos are not probed (no ffmpeg promise); a file Pillow cannot open
        simply keeps its unmeasured geometry.
        """

        if facts.width > 0 or facts.height > 0 or facts.kind != KIND_IMAGE or not facts.path:
            return facts
        try:  # pragma: no branch - single guarded import
            from PIL import Image
        except ImportError:  # pragma: no cover - Pillow is pinned in requirements
            return facts
        try:
            with Image.open(facts.path) as image:
                width, height = image.size
        except (OSError, ValueError):
            return facts
        return replace(facts, width=int(width), height=int(height))

    # ------------------------------------------------------------- measurement

    def _validated_signals(
        self, kind: str, signals: Mapping[str, float] | None
    ) -> dict[str, float]:
        table: dict[str, float] = {}
        applicable = self.scorer.applicable(kind)
        for criterion, value in (signals or {}).items():
            if criterion not in CRITERIA:
                raise QualityValidationError(f"unknown criterion {criterion!r}")
            if criterion not in applicable:
                raise QualityValidationError(
                    f"criterion {criterion!r} does not apply to {kind!r}"
                )
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise QualityValidationError(f"signal for {criterion!r} must be a number")
            if not SCORE_FLOOR <= float(value) <= SCORE_CEILING:
                raise QualityValidationError(
                    f"signal for {criterion!r} is outside {SCORE_FLOOR:.0f}–{SCORE_CEILING:.0f}"
                )
            table[criterion] = float(value)
        return table

    def _measure(self, criterion: str, facts: MediaFacts) -> CriterionScore | None:
        """The engine's own heuristic for one criterion, or None if it can't."""

        if criterion == CRITERION_COMPOSITION:
            return self._measure_composition(facts)
        if criterion == CRITERION_LIGHTING:
            return self._measure_lighting(facts)
        if criterion == CRITERION_COLOR:
            return self._measure_color(facts)
        if criterion == CRITERION_MOTION:
            return self._measure_motion(facts)
        if criterion == CRITERION_PROMPT_FIDELITY:
            return self._measure_prompt_fidelity(facts)
        # Face, hands and eyes need a detector that saw the pixels; without a
        # signal they stay unmeasured rather than invented.
        return None

    def _measure_composition(self, facts: MediaFacts) -> CriterionScore | None:
        if facts.width <= 0 or facts.height <= 0:
            return None
        components: list[float] = []
        details: list[str] = []
        if facts.aspect_ratio_expected > 0:
            actual = facts.width / facts.height
            deviation = abs(actual - facts.aspect_ratio_expected) / facts.aspect_ratio_expected
            components.append(
                _falloff(deviation, ASPECT_DEVIATION_FORGIVEN, ASPECT_DEVIATION_ZERO)
            )
            details.append(f"desvio de aspect ratio {deviation * 100:.1f}%")
        short = facts.short_side
        if short < RESOLUTION_FLOOR_PIXELS:
            components.append(SCORE_FLOOR)
            details.append(f"lado curto {short}px abaixo do piso de {RESOLUTION_FLOOR_PIXELS}px")
        else:
            components.append(
                clamp_score(SCORE_CEILING * short / RESOLUTION_TARGET_PIXELS)
            )
            details.append(f"lado curto {short}px (alvo {RESOLUTION_TARGET_PIXELS}px)")
        return CriterionScore(
            criterion=CRITERION_COMPOSITION,
            score=clamp_score(sum(components) / len(components)),
            weight=self.scorer.weight_of(CRITERION_COMPOSITION),
            source=SOURCE_MEASURED,
            detail="; ".join(details),
        )

    def _pixel_statistics(self, facts: MediaFacts) -> tuple[float, float, float] | None:
        """(mean luminance, luminance stddev, mean saturation) from the real file.

        Only images are probed — decoding video frames needs ffmpeg, which
        this environment does not promise. Any failure (no Pillow, no file,
        not an image) reads as "cannot measure", never as a score.
        """

        if facts.kind != KIND_IMAGE or not facts.path:
            return None
        try:  # pragma: no branch - single guarded import
            from PIL import Image, ImageStat
        except ImportError:  # pragma: no cover - Pillow is pinned in requirements
            return None
        try:
            with Image.open(facts.path) as image:
                grey = ImageStat.Stat(image.convert("L"))
                hsv = ImageStat.Stat(image.convert("HSV"))
        except (OSError, ValueError):
            return None
        return grey.mean[0], grey.stddev[0], hsv.mean[1]

    def _measure_lighting(self, facts: MediaFacts) -> CriterionScore | None:
        statistics = self._pixel_statistics(facts)
        if statistics is None:
            return None
        luminance, stddev, _ = statistics
        exposure = _band_score(luminance, LUMINANCE_LOW, LUMINANCE_HIGH, LUMINANCE_MAX)
        contrast = clamp_score(SCORE_CEILING * stddev / CONTRAST_TARGET_STDDEV)
        return CriterionScore(
            criterion=CRITERION_LIGHTING,
            score=clamp_score((exposure + contrast) / 2),
            weight=self.scorer.weight_of(CRITERION_LIGHTING),
            source=SOURCE_MEASURED,
            detail=f"luminância média {luminance:.0f}/255, desvio {stddev:.0f}",
        )

    def _measure_color(self, facts: MediaFacts) -> CriterionScore | None:
        statistics = self._pixel_statistics(facts)
        if statistics is None:
            return None
        _, _, saturation = statistics
        return CriterionScore(
            criterion=CRITERION_COLOR,
            score=_band_score(saturation, SATURATION_LOW, SATURATION_HIGH, SATURATION_MAX),
            weight=self.scorer.weight_of(CRITERION_COLOR),
            source=SOURCE_MEASURED,
            detail=f"saturação média {saturation:.0f}/255",
        )

    def _measure_motion(self, facts: MediaFacts) -> CriterionScore | None:
        if facts.kind != KIND_VIDEO:
            return None
        if facts.fps <= 0 and facts.duration_seconds <= 0:
            return None
        components: list[float] = []
        details: list[str] = []
        if facts.fps > 0:
            target = facts.requested_fps if facts.requested_fps > 0 else MOTION_FULL_FPS
            components.append(clamp_score(SCORE_CEILING * facts.fps / target))
            details.append(f"{facts.fps}fps (alvo {target}fps)")
        if facts.duration_seconds > 0 and facts.requested_duration > 0:
            deviation = abs(facts.duration_seconds - facts.requested_duration)
            if deviation <= DURATION_TOLERANCE_SECONDS:
                components.append(SCORE_CEILING)
            else:
                relative = deviation / facts.requested_duration
                components.append(
                    _falloff(relative, 0.0, DURATION_DEVIATION_ZERO)
                )
            details.append(
                f"duração {facts.duration_seconds:.1f}s (pedido {facts.requested_duration:.1f}s)"
            )
        return CriterionScore(
            criterion=CRITERION_MOTION,
            score=clamp_score(sum(components) / len(components)),
            weight=self.scorer.weight_of(CRITERION_MOTION),
            source=SOURCE_MEASURED,
            detail="; ".join(details),
        )

    def _measure_prompt_fidelity(self, facts: MediaFacts) -> CriterionScore | None:
        original = self._significant_tokens(facts.prompt_original)
        compiled = self._significant_tokens(facts.prompt_compiled)
        if not original or not compiled:
            return None
        retained = len(original & compiled)
        score = clamp_score(SCORE_CEILING * retained / len(original))
        return CriterionScore(
            criterion=CRITERION_PROMPT_FIDELITY,
            score=score,
            weight=self.scorer.weight_of(CRITERION_PROMPT_FIDELITY),
            source=SOURCE_MEASURED,
            detail=f"{retained} de {len(original)} termos do prompt preservados na compilação",
        )

    @staticmethod
    def _significant_tokens(text: str) -> set[str]:
        cleaned = "".join(ch if ch.isalnum() else " " for ch in text.lower())
        return {
            token
            for token in cleaned.split()
            if len(token) >= FIDELITY_MIN_TOKEN_LENGTH
        }
