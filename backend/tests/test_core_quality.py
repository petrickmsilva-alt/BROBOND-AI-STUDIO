"""ETAPA 14 tests — the quality gate on rendered output.

The defect, reproduced before anything was written: a provider returned a path
that did not exist and dimensions contradicting the requested aspect ratio, and
the worker persisted it, set `output_url`, and marked the job `complete`.
`GenerationOutput.width` and `.height` were read by no code in the repository.

These tests pin the fix at three levels: the gate's rules, the worker refusing a
bad render, and the API saying plainly what it does and does not judge.
"""
from __future__ import annotations

import pathlib
from dataclasses import dataclass

import pytest

from app.core.contracts import GenerationKind, GenerationSpec
from app.core.quality import (
    ASPECT_RATIOS,
    ASPECT_TOLERANCE,
    FAIL,
    MIN_SIDE_PIXELS,
    PASS,
    VERDICTS,
    WARN,
    MeasuredOutput,
    QualityGate,
)


@pytest.fixture()
def gate() -> QualityGate:
    return QualityGate()


@pytest.fixture()
def real_file(tmp_path) -> pathlib.Path:
    target = tmp_path / "render.png"
    target.write_bytes(b"\x89PNG fake payload")
    return target


def _spec(**overrides) -> GenerationSpec:
    base = dict(prompt_original="x", prompt_compiled="y", aspect_ratio="16:9")
    base.update(overrides)
    return GenerationSpec(**base)


def _video_spec(**overrides) -> GenerationSpec:
    base = dict(
        prompt_original="x",
        prompt_compiled="y",
        aspect_ratio="16:9",
        duration=5.0,
        fps=24,
        kind=GenerationKind.VIDEO,
    )
    base.update(overrides)
    return GenerationSpec(**base)


@dataclass
class FakeOutput:
    """Stands in for either provider output dataclass."""

    path: str
    width: int = 0
    height: int = 0
    duration_seconds: float = 0.0
    fps: int = 0
    size_bytes: int | None = None


# ---------------------------------------------------------------------------
# Measurement
# ---------------------------------------------------------------------------


def test_a_missing_file_is_minus_one_not_zero(gate: QualityGate) -> None:
    """Missing and empty must stay two different findings."""

    assert gate.size_of("/definitely/not/here.png") == -1


def test_an_empty_file_is_zero(gate: QualityGate, tmp_path) -> None:
    empty = tmp_path / "empty.png"
    empty.write_bytes(b"")
    assert gate.size_of(str(empty)) == 0


def test_size_of_survives_a_nonsense_path(gate: QualityGate) -> None:
    assert gate.size_of("") == -1
    assert gate.size_of("\x00bad") == -1


def test_measure_only_measures_the_bytes(gate: QualityGate, real_file) -> None:
    """Geometry stays as the producer reported it; nothing is guessed."""

    measured = gate.measure(FakeOutput(str(real_file), width=640, height=360))
    assert measured.size_bytes == real_file.stat().st_size
    assert (measured.width, measured.height) == (640, 360)


def test_a_directory_is_not_a_file(gate: QualityGate, tmp_path) -> None:
    assert gate.size_of(str(tmp_path)) == -1


# ---------------------------------------------------------------------------
# Existence
# ---------------------------------------------------------------------------


def test_a_render_that_was_never_written_fails(gate: QualityGate) -> None:
    report = gate.assess(_spec(), FakeOutput("/nope/missing.png", 1280, 720, size_bytes=-1))
    assert report.verdict == FAIL
    assert report.ok is False
    assert {f["rule"] for f in report.violations} >= {"file-present"}


def test_an_empty_path_is_its_own_finding(gate: QualityGate) -> None:
    report = gate.assess(_spec(), FakeOutput("", 1280, 720, size_bytes=-1))
    assert any("no path" in f["detail"] for f in report.violations)


def test_an_empty_file_fails_separately_from_a_missing_one(
    gate: QualityGate, tmp_path
) -> None:
    empty = tmp_path / "zero.png"
    empty.write_bytes(b"")
    report = gate.assess(_spec(), gate.measure(FakeOutput(str(empty), 1280, 720)))
    rules = {f["rule"] for f in report.violations}
    assert "file-not-empty" in rules
    assert "file-present" not in rules, "the file exists; it is just empty"


def test_a_real_file_of_the_right_shape_passes(gate: QualityGate, real_file) -> None:
    report = gate.assess(_spec(), gate.measure(FakeOutput(str(real_file), 1280, 720)))
    assert report.verdict == PASS
    assert report.ok is True
    assert report.findings == ()
    assert report.structural_score == 1.0


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ratio,width,height",
    [("16:9", 1280, 720), ("9:16", 720, 1280), ("1:1", 1024, 1024), ("4:3", 1024, 768), ("3:4", 768, 1024)],
)
def test_every_declared_aspect_ratio_is_accepted_when_honoured(
    gate: QualityGate, real_file, ratio, width, height
) -> None:
    report = gate.assess(_spec(aspect_ratio=ratio), gate.measure(FakeOutput(str(real_file), width, height)))
    assert report.verdict == PASS, (ratio, [f["detail"] for f in report.findings])


def test_a_square_render_cannot_pass_as_widescreen(gate: QualityGate, real_file) -> None:
    report = gate.assess(_spec(aspect_ratio="16:9"), gate.measure(FakeOutput(str(real_file), 512, 512)))
    assert report.verdict == FAIL
    finding = next(f for f in report.violations if f["rule"] == "aspect-ratio")
    assert "43.7% off" in finding["detail"]


def test_small_rounding_is_tolerated(gate: QualityGate, real_file) -> None:
    """A pipeline snapping to a multiple of eight must not be reported as broken."""

    exact = ASPECT_RATIOS["16:9"]
    nudged = int(round(720 * exact / 8) * 8)
    report = gate.assess(_spec(aspect_ratio="16:9"), gate.measure(FakeOutput(str(real_file), nudged, 720)))
    assert report.verdict == PASS, [f["detail"] for f in report.findings]


def test_just_outside_the_tolerance_fails(gate: QualityGate, real_file) -> None:
    """Pins the tolerance as a real boundary rather than a vague notion."""

    width = int(round(720 * ASPECT_RATIOS["16:9"] * (1 + ASPECT_TOLERANCE * 3)))
    report = gate.assess(_spec(aspect_ratio="16:9"), gate.measure(FakeOutput(str(real_file), width, 720)))
    assert any(f["rule"] == "aspect-ratio" for f in report.violations)


def test_an_unknown_aspect_ratio_is_reported_not_ignored(gate: QualityGate, real_file) -> None:
    report = gate.assess(_spec(aspect_ratio="21:9"), gate.measure(FakeOutput(str(real_file), 1280, 720)))
    assert any("unknown aspect ratio" in f["detail"] for f in report.violations)


def test_a_tiny_render_fails_the_floor(gate: QualityGate, real_file) -> None:
    report = gate.assess(_spec(aspect_ratio="1:1"), gate.measure(FakeOutput(str(real_file), 32, 32)))
    assert any(f["rule"] == "resolution-floor" for f in report.violations)


def test_the_floor_is_the_short_side(gate: QualityGate, real_file) -> None:
    """1280 wide is not enough if the other side is 8 pixels."""

    report = gate.assess(_spec(aspect_ratio="1:1"), gate.measure(FakeOutput(str(real_file), 1280, 8)))
    assert any(f["rule"] == "resolution-floor" for f in report.violations)
    assert MIN_SIDE_PIXELS == 64


def test_an_image_with_no_reported_dimensions_fails(gate: QualityGate, real_file) -> None:
    """`GenerationOutput` carries width and height as required fields."""

    report = gate.assess(_spec(), gate.measure(FakeOutput(str(real_file), 0, 0)))
    assert any(f["rule"] == "dimensions-reported" for f in report.violations)


def test_a_video_with_no_geometry_only_warns(gate: QualityGate, tmp_path) -> None:
    """`VideoGenerationOutput` carries duration and fps, and no geometry at all.

    Demanding dimensions of it would fail every video job in the system.
    """

    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"fake")
    output = FakeOutput(str(clip), 0, 0, duration_seconds=5.0, fps=24)
    report = gate.assess(_video_spec(), gate.measure(output))
    assert report.verdict == WARN, [f["detail"] for f in report.findings]
    assert report.ok is True, "an unreported geometry must not block delivery"
    assert any(f["rule"] == "dimensions-reported" and f["status"] == "warning" for f in report.warnings)


# ---------------------------------------------------------------------------
# Video
# ---------------------------------------------------------------------------


def test_a_video_of_the_right_length_passes(gate: QualityGate, tmp_path) -> None:
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"fake")
    output = FakeOutput(str(clip), 1280, 720, duration_seconds=5.0, fps=24)
    assert gate.assess(_video_spec(), gate.measure(output)).verdict == PASS


def test_a_short_video_fails(gate: QualityGate, tmp_path) -> None:
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"fake")
    output = FakeOutput(str(clip), 1280, 720, duration_seconds=2.0, fps=24)
    report = gate.assess(_video_spec(duration=5.0), gate.measure(output))
    assert any(f["rule"] == "duration" for f in report.violations)


def test_a_wrong_frame_rate_warns_but_does_not_block(gate: QualityGate, tmp_path) -> None:
    """Re-encoding to 30fps is recoverable; a missing file is not."""

    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"fake")
    output = FakeOutput(str(clip), 1280, 720, duration_seconds=5.0, fps=30)
    report = gate.assess(_video_spec(fps=24), gate.measure(output))
    assert report.verdict == WARN
    assert report.ok is True
    assert any(f["rule"] == "frame-rate" for f in report.warnings)


def test_image_checks_ignore_duration(gate: QualityGate, real_file) -> None:
    report = gate.assess(_spec(), gate.measure(FakeOutput(str(real_file), 1280, 720, duration_seconds=0.0)))
    assert not any(f["rule"] == "duration" for f in report.findings)


def test_a_png_named_mp4_is_flagged_not_rejected(gate: QualityGate, tmp_path) -> None:
    odd = tmp_path / "render.mp4"
    odd.write_bytes(b"fake")
    report = gate.assess(_spec(), gate.measure(FakeOutput(str(odd), 1280, 720)))
    assert report.verdict == WARN
    assert any(f["rule"] == "container" for f in report.warnings)


# ---------------------------------------------------------------------------
# Verdict and score
# ---------------------------------------------------------------------------


def test_the_verdict_vocabulary_is_closed() -> None:
    assert VERDICTS == (PASS, WARN, FAIL)


def test_warnings_alone_keep_a_render_deliverable(gate: QualityGate, tmp_path) -> None:
    odd = tmp_path / "render.mp4"
    odd.write_bytes(b"fake")
    assert gate.assess(_spec(), gate.measure(FakeOutput(str(odd), 1280, 720))).ok is True


def test_a_single_violation_blocks(gate: QualityGate, real_file) -> None:
    report = gate.assess(_spec(aspect_ratio="1:1"), gate.measure(FakeOutput(str(real_file), 1280, 720)))
    assert report.ok is False
    assert report.verdict == FAIL


def test_the_score_is_the_share_of_checks_that_passed(gate: QualityGate, real_file) -> None:
    report = gate.assess(_spec(aspect_ratio="1:1"), gate.measure(FakeOutput(str(real_file), 1280, 720)))
    assert report.structural_score == pytest.approx(
        round(report.checks_passed / report.checks_run, 4)
    )
    assert 0.0 < report.structural_score < 1.0


def test_the_score_is_not_an_aesthetic_rating() -> None:
    """A perfect structural score says nothing about whether the image is good."""

    note = QualityGate().capabilities()["note"]
    assert "structural" in note
    assert "no aesthetic score" in note


def test_the_report_separates_violations_from_warnings(gate: QualityGate, tmp_path) -> None:
    odd = tmp_path / "render.mp4"
    odd.write_bytes(b"fake")
    report = gate.assess(_spec(aspect_ratio="1:1"), gate.measure(FakeOutput(str(odd), 1280, 720)))
    assert report.violations and report.warnings
    assert {f["status"] for f in report.violations} == {"violation"}
    assert {f["status"] for f in report.warnings} == {"warning"}


def test_the_facts_record_what_was_compared(gate: QualityGate, real_file) -> None:
    facts = gate.assess(_spec(aspect_ratio="16:9"), gate.measure(FakeOutput(str(real_file), 512, 512))).facts
    assert facts["requested_aspect_ratio"] == "16:9"
    assert (facts["width"], facts["height"]) == (512, 512)
    assert facts["dimensions_source"] == "provider-report", "the claim's origin must be visible"


def test_to_dict_is_json_shaped(gate: QualityGate, real_file) -> None:
    import json

    payload = gate.assess(_spec(), gate.measure(FakeOutput(str(real_file), 1280, 720))).to_dict()
    assert json.loads(json.dumps(payload))["verdict"] == PASS


# ---------------------------------------------------------------------------
# Honesty about what cannot be checked
# ---------------------------------------------------------------------------


def test_verify_dimensions_says_so_when_no_reader_is_installed(gate: QualityGate, real_file) -> None:
    """Never report a verification that was not performed."""

    result = gate.verify_dimensions(str(real_file), 1280, 720)
    try:
        import PIL  # noqa: F401
    except ImportError:
        assert result["verified"] is False
        assert "Pillow" in result["reason"]
        assert result["reported"] == [1280, 720]
    else:
        assert result["verified"] is True
        assert result["matches"] is False


def test_capabilities_names_what_is_not_assessed(gate: QualityGate) -> None:
    capabilities = gate.capabilities()
    assert capabilities["model_loaded"] is False
    for absent in ("composition", "aesthetic quality", "prompt adherence"):
        assert absent in capabilities["does_not_assess"]


def test_every_rule_the_gate_can_raise_is_documented(gate: QualityGate) -> None:
    """A verdict must be explainable without reading the source."""

    documented = {rule["rule"] for rule in gate.rules()}
    raisable = {
        "file-present", "file-not-empty", "dimensions-reported", "resolution-floor",
        "aspect-ratio", "duration", "frame-rate", "container",
    }
    assert documented == raisable


def test_rules_declare_their_blocking_behaviour(gate: QualityGate) -> None:
    for rule in gate.rules():
        assert rule["status"].startswith(("violation", "warning"))
        assert rule["detail"]


def test_the_gate_is_deterministic(gate: QualityGate, real_file) -> None:
    """The same spec and the same artifact must give the same answer.

    One spec instance is reused on purpose: `GenerationSpec.spec_id` is a fresh
    uuid per construction, so two specs would differ on that field alone and the
    comparison would prove nothing.
    """

    spec = _spec()
    first = gate.assess(spec, gate.measure(FakeOutput(str(real_file), 1280, 720))).to_dict()
    second = gate.assess(spec, gate.measure(FakeOutput(str(real_file), 1280, 720))).to_dict()
    assert first == second


def test_two_specs_differ_only_by_their_generated_id(gate: QualityGate, real_file) -> None:
    first = gate.assess(_spec(), gate.measure(FakeOutput(str(real_file), 1280, 720))).to_dict()
    second = gate.assess(_spec(), gate.measure(FakeOutput(str(real_file), 1280, 720))).to_dict()
    assert first["spec_id"] != second["spec_id"]
    first.pop("spec_id")
    second.pop("spec_id")
    assert first == second, "the verdict must not depend on which spec instance was used"


# ---------------------------------------------------------------------------
# The worker
# ---------------------------------------------------------------------------


@pytest.fixture()
def inference_on(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "inference_enabled", True)
    monkeypatch.setattr(settings, "storage_enabled", False)
    return settings


def test_the_worker_refuses_a_render_that_was_never_written(inference_on, monkeypatch) -> None:
    """The original defect, end to end: this used to be reported `complete`."""

    from app.providers.image import GenerationOutput

    from app.queue import process_generation
    from app.schemas import GenerationType, Job
    from app.store import store

    import app.providers.image as image_module

    class LyingProvider:
        def __init__(self, model_id: str = "x") -> None:
            pass

        def generate(self, spec, output_dir):
            return GenerationOutput("/tmp/does-not-exist.png", 512, 512)

    monkeypatch.setattr(image_module, "FluxDiffusersProvider", LyingProvider)

    job = store.add_job(Job(type=GenerationType.IMAGE, prompt="x", parameters={}))
    result = process_generation(str(job.id))

    assert result["status"] == "failed"
    assert "Quality gate" in result["error"]
    assert "file-present" in result["error"]
    assert job.output_url is None, "a job that produced nothing must not carry an output URL"


def test_the_worker_refuses_a_frame_that_contradicts_the_spec(
    inference_on, monkeypatch, tmp_path
) -> None:
    from app.providers.image import GenerationOutput

    from app.queue import process_generation
    from app.schemas import GenerationType, Job
    from app.store import store

    import app.providers.image as image_module

    target = tmp_path / "square.png"
    target.write_bytes(b"\x89PNG fake")

    class WrongShape:
        def __init__(self, model_id: str = "x") -> None:
            pass

        def generate(self, spec, output_dir):
            return GenerationOutput(str(target), 512, 512)

    monkeypatch.setattr(image_module, "FluxDiffusersProvider", WrongShape)

    job = store.add_job(
        Job(type=GenerationType.IMAGE, prompt="x", parameters={"aspect_ratio": "16:9"})
    )
    result = process_generation(str(job.id))
    assert result["status"] == "failed"
    assert "aspect-ratio" in result["error"]


def test_the_worker_completes_a_render_that_satisfies_the_spec(
    inference_on, monkeypatch, tmp_path
) -> None:
    from app.providers.image import GenerationOutput

    from app.queue import process_generation
    from app.schemas import GenerationType, Job
    from app.store import store

    import app.providers.image as image_module

    target = tmp_path / "good.png"
    target.write_bytes(b"\x89PNG fake")

    class HonestProvider:
        def __init__(self, model_id: str = "x") -> None:
            pass

        def generate(self, spec, output_dir):
            return GenerationOutput(str(target), 1024, 576)

    monkeypatch.setattr(image_module, "FluxDiffusersProvider", HonestProvider)

    job = store.add_job(
        Job(type=GenerationType.IMAGE, prompt="x", parameters={"aspect_ratio": "16:9"})
    )
    assert process_generation(str(job.id))["status"] == "complete"


def test_the_gate_runs_before_the_output_is_persisted() -> None:
    """Order matters: a rejected render must never reach storage."""

    source = pathlib.Path("backend/app/queue.py").read_text()
    assert source.index("quality_gate.assess") < source.index("storage.save_path")


def test_the_worker_and_the_api_share_one_gate() -> None:
    import app.main as main_module
    import app.queue as queue_module

    assert main_module.quality_gate is not None
    assert queue_module.quality_gate is not None
    assert main_module.quality_gate.aspect_tolerance == queue_module.quality_gate.aspect_tolerance


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app
    from app.storage import storage

    monkeypatch.setattr(storage, "local_root", tmp_path)
    return TestClient(app)


def _put(tmp_path, name: str, payload: bytes = b"x" * 100) -> str:
    (tmp_path / "ws").mkdir(exist_ok=True)
    target = tmp_path / "ws" / name
    target.write_bytes(payload)
    return f"ws/{name}"


def test_the_assess_endpoint_passes_a_good_render(client, tmp_path) -> None:
    key = _put(tmp_path, "good.png")
    body = client.post(
        "/api/v1/core/quality/assess",
        json={"object_key": key, "kind": "image", "width": 1280, "height": 720},
    ).json()
    assert body["verdict"] == "pass"
    assert body["ok"] is True
    assert body["structural_score"] == 1.0
    assert body["violations"] == []


def test_the_assess_endpoint_reports_a_wrong_frame(client, tmp_path) -> None:
    key = _put(tmp_path, "square.png")
    body = client.post(
        "/api/v1/core/quality/assess",
        json={"object_key": key, "width": 720, "height": 720, "aspect_ratio": "16:9"},
    ).json()
    assert body["ok"] is False
    assert {f["rule"] for f in body["violations"]} == {"aspect-ratio"}


def test_the_assess_endpoint_reports_a_missing_object(client, tmp_path) -> None:
    (tmp_path / "ws").mkdir(exist_ok=True)
    body = client.post(
        "/api/v1/core/quality/assess",
        json={"object_key": "ws/absent.png", "width": 1280, "height": 720},
    ).json()
    assert {f["rule"] for f in body["violations"]} == {"file-present"}


def test_the_assess_endpoint_refuses_a_traversal_key(client) -> None:
    """The key is resolved through the storage guard, never opened directly."""

    response = client.post(
        "/api/v1/core/quality/assess",
        json={"object_key": "../etc/passwd", "width": 100, "height": 100},
    )
    assert response.status_code == 400


def test_the_assess_endpoint_checks_video_runtime(client, tmp_path) -> None:
    key = _put(tmp_path, "clip.mp4")
    body = client.post(
        "/api/v1/core/quality/assess",
        json={
            "object_key": key,
            "kind": "video",
            "width": 1280,
            "height": 720,
            "duration_seconds": 2.0,
            "fps": 24,
            "requested_duration": 5.0,
        },
    ).json()
    assert {f["rule"] for f in body["violations"]} == {"duration"}


def test_the_rules_endpoint_declares_its_limits(client) -> None:
    body = client.get("/api/v1/core/quality/rules").json()
    assert body["model_loaded"] is False
    assert "aesthetic quality" in body["does_not_assess"]
    assert len(body["rules"]) == len(body["assesses"])


@pytest.mark.parametrize(
    "payload",
    [
        {"object_key": ""},
        {"object_key": "a.png", "width": -1},
        {"object_key": "a.png", "height": -1},
        {"object_key": "a.png", "fps": -1},
        {"object_key": "a.png", "fps": 999},
        {"object_key": "a.png", "aspect_ratio": "21:9"},
        {"object_key": "a.png", "kind": "audio"},
        {"object_key": "a.png", "requested_duration": 0},
        {"object_key": "a.png", "requested_fps": 0},
    ],
)
def test_the_assess_endpoint_validates_its_input(client, payload) -> None:
    assert client.post("/api/v1/core/quality/assess", json=payload).status_code == 422


def test_a_zero_fps_is_accepted_as_not_reported(client, tmp_path) -> None:
    """Zero means the producer said nothing, not that the rate is invalid."""

    key = _put(tmp_path, "plain.png")
    body = client.post(
        "/api/v1/core/quality/assess",
        json={"object_key": key, "width": 1280, "height": 720, "fps": 0},
    ).json()
    assert body["verdict"] == "pass"


def test_the_quality_routes_hold_no_thresholds_of_their_own() -> None:
    import ast

    tree = ast.parse(pathlib.Path("backend/app/main.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "assess_quality":
            source = ast.unparse(node)
            assert "0.03" not in source
            assert "16 / 9" not in source
            assert "min_side" not in source
            return
    raise AssertionError("assess_quality is not defined")


def test_the_core_gate_never_shells_out() -> None:
    import ast

    tree = ast.parse(pathlib.Path("backend/app/core/quality.py").read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    # `PIL` is allowed: it is an optional import *inside* `verify_dimensions`,
    # wrapped in try/except ImportError, so the module still loads and stays
    # independent when Pillow is absent. What is banned is a framework.
    assert imported <= {"__future__", "dataclasses", "pathlib", "contracts", "PIL"}, sorted(imported)
    for banned in ("fastapi", "starlette", "sqlalchemy", "celery", "boto3", "subprocess"):
        assert banned not in imported


# ---------------------------------------------------------------------------
# Corners of the report contract
# ---------------------------------------------------------------------------


def test_measured_output_reports_existence_from_the_size() -> None:
    assert MeasuredOutput(path="a", size_bytes=0).exists is True
    assert MeasuredOutput(path="a", size_bytes=-1).exists is False


def test_measured_output_serialises() -> None:
    payload = MeasuredOutput(path="a.png", width=8, height=4, size_bytes=12).to_dict()
    assert payload["exists"] is True
    assert payload["size_bytes"] == 12


def test_a_report_with_no_checks_scores_zero() -> None:
    """Learned nothing must not read as "it is fine".

    `assess` always runs at least the existence check, so this is reachable only
    by constructing the report directly — which is a public dataclass, so the
    guard is not dead, it is just not reachable from the gate.
    """

    from app.core.quality import QualityReport

    empty = QualityReport(spec_id="x", kind="image", verdict=PASS, findings=(), checks_run=0, checks_passed=0)
    assert empty.structural_score == 0.0


def test_an_output_that_was_never_measured_is_stat_ed_by_the_gate(
    gate: QualityGate, real_file
) -> None:
    """Passing a raw provider output works too; the gate measures what it can."""

    @dataclass
    class Bare:
        path: str
        width: int
        height: int

    report = gate.assess(_spec(), Bare(str(real_file), 1280, 720))
    assert report.verdict == PASS
    assert report.facts["size_bytes"] == real_file.stat().st_size


def test_size_of_returns_minus_one_when_the_os_refuses(gate: QualityGate, tmp_path) -> None:
    """A path the OS will not even parse is a missing file, not a crash."""

    blocked = tmp_path / "no-access"
    blocked.write_bytes(b"x")
    blocked.chmod(0o000)
    unreadable = str(blocked / "inside-a-file")
    try:
        assert gate.size_of(unreadable) == -1
    finally:
        blocked.chmod(0o644)
