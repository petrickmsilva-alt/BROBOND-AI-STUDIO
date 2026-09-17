"""V3.4 — Quality AI Engine.

A render in, an honest 0–100 verdict out: eight weighted criteria (face,
hands, eyes, composition, lighting, color, motion, prompt fidelity), a
persisted report (issues, strengths, suggestions), and a recommendation —
retry below 70, manual review at 70–84, approved at 85+, masterpiece at
95+. The engine only recommends; nothing regenerates, upscales or approves
automatically.

Layering (same rule as ``campaign/`` and ``continuity/``): ``quality_score``
and ``quality_rules`` are framework-free and reason over plain data;
``quality_engine`` composes them and probes real files (Pillow) without
touching any framework; ``quality_models`` holds the SQLAlchemy table;
``quality_repository`` is the only module that touches the database.

Honesty (``SYSTEM_PROMPT.md``): every criterion's number states its source —
``measured`` (computed here from the artifact and the spec) or ``detector``
(supplied by the caller from an external detector). A criterion nothing
measured is excluded from the weighted mean and listed in ``unmeasured``,
never averaged in as an invented number. The structural ``core/quality.py``
gate (ETAPA 14) is untouched: it still decides whether an artifact exists at
all; this domain judges how good an existing artifact is.

The Provider Registry and the Director AI are not altered (sprint
pré-requisitos): the engine evaluates outputs, it neither selects providers
nor plans scenes.
"""
from .quality_engine import (
    ASPECT_DEVIATION_FORGIVEN,
    ASPECT_DEVIATION_ZERO,
    CONTRAST_TARGET_STDDEV,
    DURATION_DEVIATION_ZERO,
    DURATION_TOLERANCE_SECONDS,
    FIDELITY_MIN_TOKEN_LENGTH,
    LUMINANCE_HIGH,
    LUMINANCE_LOW,
    LUMINANCE_MAX,
    MOTION_FULL_FPS,
    MediaFacts,
    QUALITY_ENGINE_VERSION,
    QualityAssessment,
    QualityEngine,
    RESOLUTION_FLOOR_PIXELS,
    RESOLUTION_TARGET_PIXELS,
    SATURATION_HIGH,
    SATURATION_LOW,
    SATURATION_MAX,
    SOURCE_DETECTOR,
    SOURCE_MEASURED,
    SOURCES,
)
from .quality_models import (
    QualityReportRow,
    SCORE_MAX,
    SCORE_MIN,
    dumps_report,
    loads_report,
    utcnow,
)
from .quality_repository import (
    DECISION_APPROVE,
    DECISION_REGENERATE,
    DECISION_UPSCALE,
    DECISIONS,
    QualityReportView,
    QualityRepository,
    UnknownAssetError,
    UnknownReportError,
    quality_repo,
)
from .quality_rules import (
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
    UPSCALE_ELIGIBLE_STATUSES,
    UPSCALE_SHORT_SIDE_BELOW,
    build_findings,
    decide,
    status_for,
)
from .quality_score import (
    CRITERIA,
    CRITERION_COLOR,
    CRITERION_COMPOSITION,
    CRITERION_EYES,
    CRITERION_FACE,
    CRITERION_HANDS,
    CRITERION_LIGHTING,
    CRITERION_MOTION,
    CRITERION_PROMPT_FIDELITY,
    CRITERION_ROUND_DIGITS,
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
    ScoreBreakdown,
    VIDEO_CRITERIA,
    clamp_score,
)

__all__ = [name for name in dir() if not name.startswith("_")]
