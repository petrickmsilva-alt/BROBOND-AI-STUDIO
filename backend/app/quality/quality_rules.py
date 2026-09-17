"""V3.4 — Quality Rules: decision bands, findings and recommendations.

This module owns every threshold the Quality Engine decides with, so no
other file needs a magic number:

* the **decision bands** from the sprint (ETAPA 4): below 70 → retry,
  70–84 → manual review, 85 and above → approved, 95 and above →
  masterpiece;
* the **finding bands** for per-criterion prose: a criterion below 60 is an
  issue, at 85 or above it is a strength, and every issue carries a concrete
  suggestion;
* the **upscale rule**: recommended only when the render is *good* (approved
  or better) but small (short side under 1024px) — upscaling a broken render
  wastes GPU time on a defect the retry should fix first.

The rules only *recommend*. Nothing here (and nothing downstream of here)
executes a retry, an upscale or an approval automatically — the sprint is
explicit ("Não executar retry automaticamente. Apenas recomendar."), and the
decision endpoint records what the operator chose.

Independence: imports the score vocabulary from ``quality_score`` only.
"""
from __future__ import annotations

from dataclasses import dataclass

from .quality_score import (
    CRITERION_COLOR,
    CRITERION_COMPOSITION,
    CRITERION_EYES,
    CRITERION_FACE,
    CRITERION_HANDS,
    CRITERION_LIGHTING,
    CRITERION_MOTION,
    CRITERION_PROMPT_FIDELITY,
    QualityValidationError,
    SCORE_CEILING,
    SCORE_FLOOR,
    ScoreBreakdown,
)

# ---------------------------------------------------------------- decision bands

#: SPRINT V3.4 ETAPA 4 — the four bands, expressed as the three boundaries.
RETRY_BELOW = 70
APPROVED_AT = 85
MASTERPIECE_AT = 95

STATUS_RETRY = "retry"
STATUS_MANUAL_REVIEW = "manual_review"
STATUS_APPROVED = "approved"
STATUS_MASTERPIECE = "masterpiece"

#: Ordered worst → best; the UI and the repository validate against this.
QUALITY_STATUSES: tuple[str, ...] = (
    STATUS_RETRY,
    STATUS_MANUAL_REVIEW,
    STATUS_APPROVED,
    STATUS_MASTERPIECE,
)

# ---------------------------------------------------------------- finding bands

#: A criterion below this is reported as an issue (with a suggestion).
ISSUE_BELOW = 60.0

#: A criterion at or above this is reported as a strength.
STRENGTH_AT = 85.0

# ------------------------------------------------------------------ upscale rule

#: Upscale is only worth recommending when the render already earned its
#: pixels: approved or better, but with a short side under this many pixels.
UPSCALE_SHORT_SIDE_BELOW = 1024

#: Statuses good enough that enlarging the render is the next step.
UPSCALE_ELIGIBLE_STATUSES: tuple[str, ...] = (STATUS_APPROVED, STATUS_MASTERPIECE)

# ---------------------------------------------------------------- finding prose

#: Product-facing text is Portuguese, like the rest of the studio UI.
ISSUE_TEXT: dict[str, str] = {
    CRITERION_FACE: "Rosto com baixa consistência — o detector reportou confiança insuficiente.",
    CRITERION_HANDS: "Mãos com anatomia problemática — dedos ou proporções fora do esperado.",
    CRITERION_EYES: "Olhos assimétricos ou sem foco — o olhar não sustenta close-up.",
    CRITERION_COMPOSITION: "Composição fora do enquadramento pedido — geometria distante do aspect ratio ou resolução abaixo do piso.",
    CRITERION_LIGHTING: "Iluminação desequilibrada — exposição fora da faixa útil ou contraste insuficiente.",
    CRITERION_COLOR: "Cor fora da paleta útil — saturação inadequada para entrega.",
    CRITERION_MOTION: "Movimento abaixo do padrão — frame rate ou duração não sustentam o vídeo.",
    CRITERION_PROMPT_FIDELITY: "Baixa fidelidade ao prompt — o resultado se afastou do que foi pedido.",
}

STRENGTH_TEXT: dict[str, str] = {
    CRITERION_FACE: "Rosto consistente e bem resolvido.",
    CRITERION_HANDS: "Mãos anatomicamente corretas.",
    CRITERION_EYES: "Olhos nítidos e simétricos.",
    CRITERION_COMPOSITION: "Composição fiel ao enquadramento pedido.",
    CRITERION_LIGHTING: "Iluminação equilibrada, exposição na faixa ideal.",
    CRITERION_COLOR: "Paleta de cor sólida e bem saturada.",
    CRITERION_MOTION: "Movimento fluido no frame rate pedido.",
    CRITERION_PROMPT_FIDELITY: "Alta fidelidade ao prompt original.",
}

SUGGESTION_TEXT: dict[str, str] = {
    CRITERION_FACE: "Reforce a identidade: use o LoRA da persona ou um identity lock de continuidade.",
    CRITERION_HANDS: "Adicione o guard negativo de mãos e regenere com outro seed.",
    CRITERION_EYES: "Peça close-up com foco nos olhos ou aplique inpainting na região ocular.",
    CRITERION_COMPOSITION: "Regenere com o aspect ratio correto ou reenquadre no formato pedido.",
    CRITERION_LIGHTING: "Especifique o esquema de luz (ex. warm tungsten, blue hour) no prompt.",
    CRITERION_COLOR: "Declare a paleta desejada no prompt ou aplique color grading na entrega.",
    CRITERION_MOTION: "Regenere pedindo 24fps ou mais e confirme a duração no spec.",
    CRITERION_PROMPT_FIDELITY: "Simplifique o prompt em blocos e recompile pelo PromptCompiler.",
}


@dataclass(frozen=True)
class QualityDecision:
    """What the bands say about one overall score. A recommendation, not an act."""

    status: str
    retry_recommended: bool
    upscale_recommended: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "retry_recommended": self.retry_recommended,
            "upscale_recommended": self.upscale_recommended,
        }


def status_for(overall_score: int) -> str:
    """Map a 0–100 score onto the four bands of ETAPA 4."""

    if not SCORE_FLOOR <= overall_score <= SCORE_CEILING:
        raise QualityValidationError(
            f"overall score {overall_score} is outside {SCORE_FLOOR:.0f}–{SCORE_CEILING:.0f}"
        )
    if overall_score >= MASTERPIECE_AT:
        return STATUS_MASTERPIECE
    if overall_score >= APPROVED_AT:
        return STATUS_APPROVED
    if overall_score >= RETRY_BELOW:
        return STATUS_MANUAL_REVIEW
    return STATUS_RETRY


def decide(overall_score: int, *, short_side_pixels: int = 0) -> QualityDecision:
    """The full recommendation for one score.

    ``short_side_pixels`` of 0 means the geometry is unknown — an upscale
    cannot be recommended for pixels nobody measured.
    """

    status = status_for(overall_score)
    upscale = (
        status in UPSCALE_ELIGIBLE_STATUSES
        and 0 < short_side_pixels < UPSCALE_SHORT_SIDE_BELOW
    )
    return QualityDecision(
        status=status,
        retry_recommended=status == STATUS_RETRY,
        upscale_recommended=upscale,
    )


def build_findings(breakdown: ScoreBreakdown) -> tuple[list[str], list[str], list[str]]:
    """Issues, strengths and suggestions for one score breakdown.

    Only *measured* criteria produce findings: a criterion nothing measured is
    neither an issue nor a strength, it is listed in ``unmeasured`` by the
    scorer and stays out of the prose here.
    """

    issues: list[str] = []
    strengths: list[str] = []
    suggestions: list[str] = []
    for criterion_score in breakdown.criteria:
        if criterion_score.score < ISSUE_BELOW:
            issues.append(ISSUE_TEXT[criterion_score.criterion])
            suggestions.append(SUGGESTION_TEXT[criterion_score.criterion])
        elif criterion_score.score >= STRENGTH_AT:
            strengths.append(STRENGTH_TEXT[criterion_score.criterion])
    return issues, strengths, suggestions
