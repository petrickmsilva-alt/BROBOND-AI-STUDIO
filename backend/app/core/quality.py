"""QualityGate — assesses a generated artifact against the spec that produced it.

The defect this exists to close, reproduced end to end before a line was written:
a provider returned a path that **did not exist** and dimensions (512x512) that
contradicted the requested 16:9. The worker persisted it, set `output_url`, and
marked the job `complete`. `SYSTEM_PROMPT.md` is explicit — "Não invente arquivos,
jobs concluídos, modelos carregados ou outputs inexistentes" — and nothing in the
pipeline enforced it on the way out. `GenerationOutput.width` and `.height` were
read by no code in the repository at all.

What this gate is: a **structural** check. Existence, size, reported geometry
against the requested aspect ratio, resolution floor, and — for video — duration
and frame rate against the spec. Every one of those is a fact about the artifact
or a comparison of two declared numbers.

What it deliberately is not: an aesthetic judgement. No model is loaded and none
is pretended. There is no score for "is this a good image", because nothing here
can see the image, and inventing a number that looks like one is exactly the
failure mode `SYSTEM_PROMPT.md` forbids. `structural_score` is the fraction of
applicable structural checks that passed — nothing more, and it says so.

Responsibility boundaries:
  * it does not choose providers (registry);
  * it does not compose prompts (PromptCompiler);
  * it does not decide what to do about a failure — it reports, the caller acts.

Independence: imports `contracts` only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .contracts import GENERATION_SPEC_FIELDS, GenerationKind, GenerationSpec

#: Aspect ratios the specs actually use, as width/height.
ASPECT_RATIOS: dict[str, float] = {
    "16:9": 16 / 9,
    "9:16": 9 / 16,
    "1:1": 1.0,
    "4:3": 4 / 3,
    "3:4": 3 / 4,
}

DEFAULT_ASPECT_RATIO = "16:9"

#: Relative deviation tolerated between the requested ratio and the reported one.
#: Generous enough for the integer rounding a pipeline does on its way to a
#: multiple of eight, tight enough that a 1:1 render cannot pass as 16:9.
ASPECT_TOLERANCE = 0.03

#: Below this on either side the render is broken whatever else is true.
MIN_SIDE_PIXELS = 64

#: Video duration and frame rate are integers in the contract, so the comparison
#: is exact rather than tolerant.
DURATION_TOLERANCE_SECONDS = 1.0

PASS = "pass"
WARN = "warn"
FAIL = "fail"
VERDICTS: tuple[str, ...] = (PASS, WARN, FAIL)

VIOLATION = "violation"
WARNING = "warning"

#: Extension expected per kind, used only to flag a mismatch — never to reject.
EXPECTED_EXTENSION: dict[str, str] = {"image": "png", "video": "mp4"}


@dataclass(frozen=True)
class MeasuredOutput:
    """What is actually known about a rendered artifact.

    `size_bytes` of -1 means the file was not stat-able, which is a finding in
    its own right rather than a zero. Width and height of 0 mean the producer
    did not report them: the gate says so instead of guessing from the path.
    """

    path: str
    width: int = 0
    height: int = 0
    duration_seconds: float = 0.0
    fps: int = 0
    size_bytes: int = -1

    @property
    def exists(self) -> bool:
        return self.size_bytes >= 0

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "width": self.width,
            "height": self.height,
            "duration_seconds": self.duration_seconds,
            "fps": self.fps,
            "size_bytes": self.size_bytes,
            "exists": self.exists,
        }


@dataclass(frozen=True)
class QualityReport:
    """The gate's answer: a verdict, the findings behind it, and the facts used."""

    spec_id: str
    kind: str
    verdict: str
    findings: tuple[dict[str, str], ...]
    checks_run: int
    checks_passed: int
    facts: dict[str, object] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """True when nothing blocks delivery. Warnings do not block."""

        return self.verdict != FAIL

    @property
    def structural_score(self) -> float:
        """Fraction of applicable structural checks that passed, 0.0 to 1.0.

        Deliberately not an aesthetic score and not a percentage "quality". With
        no checks applicable — an output nothing could be said about — the score
        is 0.0, because "we learned nothing" must not read as "it is fine".
        """

        if not self.checks_run:
            return 0.0
        return round(self.checks_passed / self.checks_run, 4)

    @property
    def violations(self) -> tuple[dict[str, str], ...]:
        return tuple(f for f in self.findings if f["status"] == VIOLATION)

    @property
    def warnings(self) -> tuple[dict[str, str], ...]:
        return tuple(f for f in self.findings if f["status"] == WARNING)

    def to_dict(self) -> dict[str, object]:
        return {
            "spec_id": self.spec_id,
            "kind": self.kind,
            "verdict": self.verdict,
            "ok": self.ok,
            "structural_score": self.structural_score,
            "checks_run": self.checks_run,
            "checks_passed": self.checks_passed,
            "violations": list(self.violations),
            "warnings": list(self.warnings),
            "facts": dict(self.facts),
        }


class QualityGate:
    """Structural assessment of a rendered artifact. Deterministic; no inference."""

    def __init__(
        self,
        *,
        aspect_tolerance: float = ASPECT_TOLERANCE,
        min_side_pixels: int = MIN_SIDE_PIXELS,
    ) -> None:
        self.aspect_tolerance = aspect_tolerance
        self.min_side_pixels = min_side_pixels

    # ------------------------------------------------------------------ public

    def assess(
        self,
        spec: GenerationSpec,
        output: MeasuredOutput | object,
        *,
        kind: GenerationKind | None = None,
    ) -> QualityReport:
        """Check `output` against `spec` and report.

        `output` is anything exposing `path` and, when known, `width`, `height`,
        `duration_seconds`, `fps` and `size_bytes` — which is the shape both
        provider output dataclasses already have, so no adapter is needed.
        """

        resolved = kind or getattr(spec, "kind", GenerationKind.IMAGE)
        kind_name = resolved.value if hasattr(resolved, "value") else str(resolved)
        path = str(getattr(output, "path", "") or "")
        width = int(getattr(output, "width", 0) or 0)
        height = int(getattr(output, "height", 0) or 0)
        duration = float(getattr(output, "duration_seconds", 0.0) or 0.0)
        fps = int(getattr(output, "fps", 0) or 0)
        size_bytes = getattr(output, "size_bytes", None)
        if size_bytes is None:
            size_bytes = self.size_of(path)
        size_bytes = int(size_bytes)

        findings: list[dict[str, str]] = []
        checks_run = 0
        checks_passed = 0

        def check(rule: str, passed: bool, detail: str, *, status: str = VIOLATION) -> None:
            nonlocal checks_run, checks_passed
            checks_run += 1
            if passed:
                checks_passed += 1
                return
            findings.append({"rule": rule, "status": status, "detail": detail})

        # -- the file itself ---------------------------------------------------
        exists = size_bytes >= 0
        check(
            "file-present",
            exists,
            f"no file was produced at {path!r}" if path else "the provider returned no path",
        )
        if exists:
            check(
                "file-not-empty",
                size_bytes > 0,
                f"{path} is 0 bytes",
            )

        # -- geometry ----------------------------------------------------------
        # The two output contracts differ, and the gate follows them rather than
        # demanding the same of both: `GenerationOutput` carries width and height
        # as required fields, while `VideoGenerationOutput` carries duration and
        # fps and no geometry at all. A missing size on an image is therefore a
        # broken contract; on a video it is simply not reported, and the geometry
        # checks are skipped instead of failed.
        is_image = kind_name == GenerationKind.IMAGE.value
        if width > 0 and height > 0:
            checks_run += 1
            checks_passed += 1
        elif is_image:
            check(
                "dimensions-reported",
                False,
                "the image provider reported no usable dimensions, which its contract requires",
            )
        else:
            # Counted as passed — the video contract carries no geometry, so
            # there is nothing to fail — but still surfaced, because "the frame
            # could not be checked" is information a caller needs. A single
            # `check()` call cannot express both, so this one is explicit.
            checks_run += 1
            checks_passed += 1
            findings.append(
                {
                    "rule": "dimensions-reported",
                    "status": WARNING,
                    "detail": "the video contract reports no geometry, so the frame was not checked",
                }
            )
        if width > 0 and height > 0:
            check(
                "resolution-floor",
                min(width, height) >= self.min_side_pixels,
                f"{width}x{height} is below the {self.min_side_pixels}px floor on its short side",
            )
            requested = str(getattr(spec, "aspect_ratio", DEFAULT_ASPECT_RATIO) or DEFAULT_ASPECT_RATIO)
            expected = ASPECT_RATIOS.get(requested)
            if expected is None:
                check(
                    "aspect-ratio",
                    False,
                    f"the spec asks for an unknown aspect ratio {requested!r}",
                )
            else:
                actual = width / height
                deviation = abs(actual - expected) / expected
                check(
                    "aspect-ratio",
                    deviation <= self.aspect_tolerance,
                    f"{width}x{height} is {actual:.3f}, {deviation * 100:.1f}% off the requested "
                    f"{requested} ({expected:.3f})",
                )

        # -- video only --------------------------------------------------------
        if kind_name == GenerationKind.VIDEO.value:
            requested_duration = float(getattr(spec, "duration", 0.0) or 0.0)
            check(
                "duration",
                duration > 0 and abs(duration - requested_duration) <= DURATION_TOLERANCE_SECONDS,
                f"the render is {duration}s, the spec asked for {requested_duration}s",
            )
            requested_fps = int(getattr(spec, "fps", 0) or 0)
            if requested_fps:
                check(
                    "frame-rate",
                    fps == requested_fps,
                    f"the render is {fps}fps, the spec asked for {requested_fps}fps",
                    status=WARNING,
                )

        # -- container ---------------------------------------------------------
        expected_extension = EXPECTED_EXTENSION.get(kind_name)
        if expected_extension and path:
            suffix = Path(path).suffix.lstrip(".").lower()
            check(
                "container",
                suffix == expected_extension,
                f"a {kind_name} render came back as .{suffix or 'unknown'}, expected .{expected_extension}",
                status=WARNING,
            )

        facts: dict[str, object] = {
            "path": path,
            "exists": exists,
            "size_bytes": size_bytes,
            "width": width,
            "height": height,
            "duration_seconds": duration,
            "fps": fps,
            "requested_aspect_ratio": str(getattr(spec, "aspect_ratio", DEFAULT_ASPECT_RATIO)),
            "requested_duration": float(getattr(spec, "duration", 0.0) or 0.0),
            "requested_fps": int(getattr(spec, "fps", 0) or 0),
            #: The geometry comes from the producer's own report. Verifying it
            #: against the pixels needs an image or video probe; see
            #: `verify_dimensions`.
            "dimensions_source": "provider-report",
        }

        violations = [f for f in findings if f["status"] == VIOLATION]
        verdict = FAIL if violations else (WARN if findings else PASS)
        return QualityReport(
            spec_id=str(getattr(spec, "spec_id", "") or ""),
            kind=kind_name,
            verdict=verdict,
            findings=tuple(findings),
            checks_run=checks_run,
            checks_passed=checks_passed,
            facts=facts,
        )

    # ----------------------------------------------------------------- helpers

    @staticmethod
    def size_of(path: str) -> int:
        """Byte size of a file, or -1 when it is not there.

        -1 rather than 0 so that "missing" and "empty" stay two different
        findings: one says the provider never wrote anything, the other says it
        wrote nothing.
        """

        try:
            target = Path(path)
            return target.stat().st_size if target.is_file() else -1
        except (OSError, ValueError):
            return -1

    def measure(self, output: object) -> MeasuredOutput:
        """Attach what can be learned from the filesystem to a provider's output.

        Only the byte size is measured here. Width and height stay as the
        producer reported them: reading real pixels needs Pillow for images and
        ffprobe for video, and neither is assumed to be installed. Guessing from
        the path or the spec would be inventing a measurement.
        """

        path = str(getattr(output, "path", "") or "")
        return MeasuredOutput(
            path=path,
            width=int(getattr(output, "width", 0) or 0),
            height=int(getattr(output, "height", 0) or 0),
            duration_seconds=float(getattr(output, "duration_seconds", 0.0) or 0.0),
            fps=int(getattr(output, "fps", 0) or 0),
            size_bytes=self.size_of(path),
        )

    def verify_dimensions(self, path: str, width: int, height: int) -> dict[str, object]:
        """Compare a producer's reported geometry against the file, if possible.

        Returns `verified` False with a reason when no reader is available, so a
        caller can tell "checked and correct" from "could not check". Never
        reports a verification it did not perform.
        """

        try:
            from PIL import Image  # type: ignore[import-not-found]
        except ImportError:
            return {
                "verified": False,
                "reason": "Pillow is not installed, so the pixels were not read",
                "reported": [width, height],
            }
        try:
            with Image.open(path) as image:
                actual = image.size
        except Exception as error:  # noqa: BLE001 - an unreadable file is a finding
            return {
                "verified": False,
                "reason": f"the file could not be opened: {error}",
                "reported": [width, height],
            }
        return {
            "verified": True,
            "reason": "",
            "reported": [width, height],
            "actual": list(actual),
            "matches": list(actual) == [width, height],
        }

    # ------------------------------------------------------------------- rules

    def rules(self) -> tuple[dict[str, str], ...]:
        """Every rule this gate can raise, with what it means and how it blocks.

        Exposed so a client can explain a verdict without reading the source.
        """

        return (
            {
                "rule": "file-present",
                "status": VIOLATION,
                "detail": "a file was actually written at the reported path",
            },
            {
                "rule": "file-not-empty",
                "status": VIOLATION,
                "detail": "the file has at least one byte",
            },
            {
                "rule": "dimensions-reported",
                "status": f"{VIOLATION} (image) / {WARNING} (video)",
                "detail": (
                    "the producer reported a usable width and height. Required for images, "
                    "where the contract carries geometry; only a warning for video, where it "
                    "does not, and the geometry checks are then skipped"
                ),
            },
            {
                "rule": "resolution-floor",
                "status": VIOLATION,
                "detail": f"the short side is at least {self.min_side_pixels}px",
            },
            {
                "rule": "aspect-ratio",
                "status": VIOLATION,
                "detail": f"the frame is within {self.aspect_tolerance * 100:.0f}% of the requested ratio",
            },
            {
                "rule": "duration",
                "status": VIOLATION,
                "detail": "video: the runtime matches the spec within a second",
            },
            {
                "rule": "frame-rate",
                "status": WARNING,
                "detail": "video: the frame rate matches the spec",
            },
            {
                "rule": "container",
                "status": WARNING,
                "detail": "the file extension matches the kind that was rendered",
            },
        )

    def capabilities(self) -> dict[str, object]:
        """What this gate can and cannot judge, stated plainly.

        Exists so the API never implies an aesthetic assessment it does not do.
        """

        return {
            "assesses": [rule["rule"] for rule in self.rules()],
            "does_not_assess": [
                "composition",
                "prompt adherence",
                "anatomy or artifact detection",
                "aesthetic quality",
                "persona likeness",
            ],
            "model_loaded": False,
            "note": (
                "structural checks only: no model is loaded and no aesthetic score is "
                "produced. structural_score is the share of applicable structural checks "
                "that passed."
            ),
            "spec_fields_known": len(GENERATION_SPEC_FIELDS),
        }
