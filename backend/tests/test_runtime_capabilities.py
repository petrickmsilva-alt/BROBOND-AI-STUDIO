"""ETAPA 16 tests — runtime capability detection, preprocessing and training.

These four modules were 23%–89% covered because every path through them needs a
dependency this sandbox does not have (nvidia-smi, Pillow, controlnet-aux, a LoRA
trainer, CUDA). The absence of the dependency is exactly what they are written to
detect, so the tests assert the refusal — and where the logic behind the refusal
is pure, they substitute the dependency to reach it.
"""
from __future__ import annotations

import subprocess
import sys
import types
from pathlib import Path
from uuid import uuid4

import pytest


# ---------------------------------------------------------------------------
# system.gpu_info
# ---------------------------------------------------------------------------


def test_gpu_info_reports_no_card_when_nvidia_smi_is_absent(monkeypatch) -> None:
    from app import system

    monkeypatch.setattr(system.shutil, "which", lambda _name: None)
    assert system.gpu_info() == {
        "available": False,
        "backend": "cpu",
        "message": "nvidia-smi not found",
    }


def test_gpu_info_parses_the_smi_csv(monkeypatch) -> None:
    """The parsing is pure; only the subprocess stands in for real hardware."""

    from app import system

    monkeypatch.setattr(system.shutil, "which", lambda name: "/usr/bin/nvidia-smi")
    captured: dict = {}

    def fake_output(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return (
            "NVIDIA GeForce RTX 4090, 24564, 24000, 550.54.14\n"
            "NVIDIA GeForce RTX 3090, 24576, 1024, 550.54.14\n"
        )

    monkeypatch.setattr(system.subprocess, "check_output", fake_output)
    info = system.gpu_info()

    assert info["backend"] == "cuda"
    assert info["available"] is True
    assert len(info["gpus"]) == 2
    assert info["gpus"][0] == {
        "name": "NVIDIA GeForce RTX 4090",
        "vram_total_mb": 24564,
        "vram_free_mb": 24000,
        "driver": "550.54.14",
    }
    assert info["gpus"][1]["vram_free_mb"] == 1024
    assert captured["command"][0] == "nvidia-smi"
    assert captured["kwargs"]["timeout"] == 3, "a hung nvidia-smi must not hang the request"


def test_gpu_info_treats_empty_smi_output_as_unavailable(monkeypatch) -> None:
    from app import system

    monkeypatch.setattr(system.shutil, "which", lambda name: "/usr/bin/nvidia-smi")
    monkeypatch.setattr(system.subprocess, "check_output", lambda *a, **k: "")
    info = system.gpu_info()
    assert info["available"] is False
    assert info["backend"] == "cuda"


@pytest.mark.parametrize(
    "failure",
    [
        OSError("no such file"),
        subprocess.SubprocessError("timed out"),
        ValueError("could not convert string to float: 'N/A'"),
    ],
)
def test_gpu_info_swallows_a_broken_probe(monkeypatch, failure) -> None:
    """A broken GPU probe must degrade to CPU, never raise into a health check."""

    from app import system

    def boom(*args, **kwargs):
        raise failure

    monkeypatch.setattr(system.shutil, "which", lambda name: "/usr/bin/nvidia-smi")
    monkeypatch.setattr(system.subprocess, "check_output", boom)
    assert system.gpu_info() == {
        "available": False,
        "backend": "cpu",
        "message": "GPU detection failed",
    }


def test_gpu_info_handles_a_malformed_row(monkeypatch) -> None:
    from app import system

    monkeypatch.setattr(system.shutil, "which", lambda name: "/usr/bin/nvidia-smi")
    monkeypatch.setattr(system.subprocess, "check_output", lambda *a, **k: "only, three, fields\n")
    assert system.gpu_info()["message"] == "GPU detection failed"


# ---------------------------------------------------------------------------
# preprocessing
# ---------------------------------------------------------------------------


def test_an_unknown_mode_is_refused() -> None:
    from app.preprocessing import PreprocessingError, preprocessor

    with pytest.raises(PreprocessingError, match="Unsupported preprocessing mode: scribble"):
        preprocessor.preprocess("in.png", "scribble", "out.png")


@pytest.mark.parametrize("mode", ["edges", "depth", "tile"])
def test_pillow_modes_refuse_cleanly_when_pillow_is_missing(mode: str, monkeypatch) -> None:
    from app import preprocessing

    monkeypatch.setitem(sys.modules, "PIL", None)
    with pytest.raises(preprocessing.PreprocessingError, match="Pillow is required"):
        preprocessing.preprocessor.preprocess("in.png", mode, "out.png")


def test_openpose_refuses_cleanly_when_controlnet_aux_is_missing(monkeypatch) -> None:
    from app import preprocessing

    monkeypatch.setitem(sys.modules, "controlnet_aux", None)
    with pytest.raises(preprocessing.PreprocessingError, match="controlnet-aux is required"):
        preprocessing.preprocessor.preprocess("in.png", "pose", "out.png")


@pytest.fixture()
def fake_pil(monkeypatch):
    """A stand-in for Pillow that records what the preprocessor asked of it."""

    calls: list[str] = []

    class FakeImage:
        def __init__(self, mode: str = "RGB") -> None:
            self.mode = mode

        def convert(self, target: str) -> "FakeImage":
            calls.append(f"convert:{target}")
            return FakeImage(target)

        def filter(self, kernel) -> "FakeImage":
            calls.append(f"filter:{kernel}")
            return self

        def save(self, destination: str, format: str | None = None) -> None:
            calls.append(f"save:{Path(destination).name}:{format}")
            Path(destination).write_bytes(b"fake png")

    class FakeFilter:
        FIND_EDGES = "FIND_EDGES"

    module = types.ModuleType("PIL")
    module.Image = types.SimpleNamespace(open=lambda source: (calls.append(f"open:{source}"), FakeImage())[1])
    module.ImageFilter = FakeFilter
    monkeypatch.setitem(sys.modules, "PIL", module)
    return calls


@pytest.mark.parametrize("mode,expected", [("depth", "convert:L"), ("edges", "filter:FIND_EDGES")])
def test_pillow_modes_take_the_right_branch(fake_pil, tmp_path, mode: str, expected: str) -> None:
    from app.preprocessing import preprocessor

    destination = tmp_path / "nested" / "out.png"
    assert preprocessor.preprocess("reference.png", mode, str(destination)) == str(destination)
    assert expected in fake_pil
    assert destination.is_file(), "the parent directory must be created"


def test_tile_mode_passes_the_frame_through(fake_pil, tmp_path) -> None:
    """Tile conditioning takes the pixels as they are.

    Every mode gets the `convert("RGB")` normalisation on open; what tile must
    NOT get is the greyscale conversion of depth or the edge filter.
    """

    from app.preprocessing import preprocessor

    destination = tmp_path / "tile.png"
    preprocessor.preprocess("reference.png", "tile", str(destination))
    assert fake_pil == ["open:reference.png", "convert:RGB", "save:tile.png:PNG"], fake_pil


def test_openpose_runs_the_detector_when_it_is_installed(monkeypatch, tmp_path) -> None:
    from app import preprocessing

    seen: dict = {}

    class FakeDetector:
        @classmethod
        def from_pretrained(cls, repo: str) -> "FakeDetector":
            seen["repo"] = repo
            return cls()

        def __call__(self, source: str):
            seen["source"] = source
            return types.SimpleNamespace(save=lambda destination: Path(destination).write_bytes(b"pose"))

    module = types.ModuleType("controlnet_aux")
    module.OpenposeDetector = FakeDetector
    monkeypatch.setitem(sys.modules, "controlnet_aux", module)

    destination = tmp_path / "nested" / "pose.png"
    assert preprocessing.preprocessor.preprocess("in.png", "pose", str(destination)) == str(destination)
    assert seen == {"repo": "lllyasviel/ControlNet", "source": "in.png"}
    assert destination.is_file()


# ---------------------------------------------------------------------------
# providers/common
# ---------------------------------------------------------------------------


def test_generator_for_returns_none_for_no_seed() -> None:
    """A `None` seed must mean "let the model choose", not "seed zero"."""

    from app.providers.common import generator_for

    assert generator_for(None) is None


def test_generator_for_asks_cuda_for_a_seeded_generator(monkeypatch) -> None:
    from app.providers import common

    seen: dict = {}

    class FakeGenerator:
        def __init__(self, device: str) -> None:
            seen["device"] = device

        def manual_seed(self, seed: int) -> "FakeGenerator":
            seen["seed"] = seed
            return self

    monkeypatch.setitem(sys.modules, "torch", types.SimpleNamespace(Generator=FakeGenerator))
    assert common.generator_for(1234) is not None
    assert seen == {"device": "cuda", "seed": 1234}


def test_health_report_is_one_shape(monkeypatch) -> None:
    from app.providers.common import health_report

    report = health_report("flux-dev", reason="no GPU", available=False, loaded=False)
    assert report == {
        "available": False,
        "reason": "no GPU",
        "model_id": "flux-dev",
        "loaded": False,
    }


def test_health_report_can_claim_availability(monkeypatch) -> None:
    from app.providers.common import health_report

    report = health_report("flux-dev", reason=None, available=True, loaded=True)
    assert report["available"] is True and report["reason"] is None and report["loaded"] is True


def test_cuda_availability_reports_a_missing_torch(monkeypatch) -> None:
    from app.providers import common

    monkeypatch.setitem(sys.modules, "torch", None)
    assert common.cuda_availability() == (False, "torch is not installed")


def test_cuda_availability_reports_no_gpu(monkeypatch) -> None:
    from app.providers import common

    monkeypatch.setitem(sys.modules, "torch", types.SimpleNamespace(cuda=types.SimpleNamespace(is_available=lambda: False)))
    assert common.cuda_availability() == (False, "CUDA GPU is required")


def test_cuda_availability_reports_a_gpu(monkeypatch) -> None:
    from app.providers import common

    monkeypatch.setitem(sys.modules, "torch", types.SimpleNamespace(cuda=types.SimpleNamespace(is_available=lambda: True)))
    assert common.cuda_availability() == (True, None)


def test_apply_lora_reports_whether_it_loaded_anything() -> None:
    from app.providers.common import apply_lora

    assert apply_lora(object(), None) is False
    assert apply_lora(object(), "") is False


def test_apply_lora_loads_and_weights_the_adapter() -> None:
    from app.providers.common import PERSONA_ADAPTER_NAME, PERSONA_ADAPTER_WEIGHT, apply_lora

    calls: list = []

    class FakePipeline:
        def load_lora_weights(self, path, adapter_name):
            calls.append(("load", path, adapter_name))

        def set_adapters(self, names, adapter_weights):
            calls.append(("set", names, adapter_weights))

    assert apply_lora(FakePipeline(), "persona-abc") is True
    assert calls == [
        ("load", "persona-abc", PERSONA_ADAPTER_NAME),
        ("set", [PERSONA_ADAPTER_NAME], [PERSONA_ADAPTER_WEIGHT]),
    ]


# ---------------------------------------------------------------------------
# lora.LoRATrainer
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("count", [0, 1, 19, 51, 500])
def test_the_plan_refuses_an_unusable_reference_count(count: int) -> None:
    from app.lora import LoRATrainer

    with pytest.raises(ValueError, match="between 20 and 50 images"):
        LoRATrainer().build_plan(uuid4(), [uuid4() for _ in range(count)], "Petrick", "cinematic realism")


@pytest.mark.parametrize("count", [20, 35, 50])
def test_the_plan_accepts_a_usable_reference_count(count: int) -> None:
    from app.lora import LoRATrainer

    persona = uuid4()
    plan = LoRATrainer().build_plan(persona, [uuid4() for _ in range(count)], "Petrick", "cinematic realism")
    assert plan.persona_id == persona
    assert plan.image_count == count
    assert len(plan.captions) == count
    assert plan.captions[0] == "photo of Petrick, cinematic realism, consistent identity reference 1"
    assert plan.output_name == f"persona-{persona}-v1.safetensors"


def test_the_trainer_says_it_is_not_enabled_instead_of_pretending() -> None:
    """No GPU profile means no training. It must not report a finished run."""

    from app.lora import LoRATrainer, TrainingPlan

    plan = TrainingPlan(persona_id=uuid4(), image_count=20, captions=[], output_name="x.safetensors")
    with pytest.raises(RuntimeError, match="LoRA trainer is not enabled"):
        LoRATrainer().train(plan, "/tmp/out")


# ---------------------------------------------------------------------------
# training — dataset preparation and the execution boundary
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("count", [0, 19, 51])
def test_prepare_dataset_refuses_an_unusable_reference_count(count: int) -> None:
    from app.training import TrainingError, prepare_dataset

    with pytest.raises(TrainingError, match="between 20 and 50 reference assets"):
        prepare_dataset(uuid4(), [uuid4() for _ in range(count)], "Petrick", "cinematic realism")


def test_prepare_dataset_refuses_a_missing_asset(monkeypatch) -> None:
    from app import training

    class EmptyDb:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, model, key):
            return None

    monkeypatch.setattr(training, "SessionLocal", EmptyDb)
    monkeypatch.setattr(training.settings, "local_media_dir", "/tmp/brobond-test-media")

    with pytest.raises(training.TrainingError, match="Reference asset not found"):
        training.prepare_dataset(uuid4(), [uuid4() for _ in range(20)], "Petrick", "cinematic realism")


def _asset(kind: str = "image", name: str = "ref.png", object_key: str = "ws/ref.png"):
    return types.SimpleNamespace(kind=kind, name=name, object_key=object_key)


class _AssetDb:
    def __init__(self, asset) -> None:
        self.asset = asset

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, model, key):
        return self.asset


def test_prepare_dataset_refuses_a_non_image_reference(monkeypatch, tmp_path) -> None:
    from app import training

    monkeypatch.setattr(training, "SessionLocal", lambda: _AssetDb(_asset(kind="video", name="clip.mp4")))
    monkeypatch.setattr(training.settings, "local_media_dir", str(tmp_path))
    with pytest.raises(training.TrainingError, match="not an image: clip.mp4"):
        training.prepare_dataset(uuid4(), [uuid4() for _ in range(20)], "Petrick", "cinematic realism")


def test_prepare_dataset_refuses_when_object_storage_is_on(monkeypatch, tmp_path) -> None:
    """Downloading from MinIO is a real step; it must not be silently skipped."""

    from app import training

    monkeypatch.setattr(training, "SessionLocal", lambda: _AssetDb(_asset()))
    monkeypatch.setattr(training.settings, "local_media_dir", str(tmp_path))
    monkeypatch.setattr(training.settings, "storage_enabled", True)
    with pytest.raises(training.TrainingError, match="MinIO dataset download is required"):
        training.prepare_dataset(uuid4(), [uuid4() for _ in range(20)], "Petrick", "cinematic realism")


def test_prepare_dataset_refuses_a_missing_file(monkeypatch, tmp_path) -> None:
    from app import training

    monkeypatch.setattr(training, "SessionLocal", lambda: _AssetDb(_asset()))
    monkeypatch.setattr(training.settings, "local_media_dir", str(tmp_path))
    monkeypatch.setattr(training.settings, "storage_enabled", False)
    monkeypatch.setattr(training.storage, "local_root", tmp_path)
    with pytest.raises(training.TrainingError, match="Reference file is missing"):
        training.prepare_dataset(uuid4(), [uuid4() for _ in range(20)], "Petrick", "cinematic realism")


def test_prepare_dataset_writes_a_captioned_manifest(monkeypatch, tmp_path) -> None:
    """The happy path: files copied with stable names and one caption line each."""

    import json as jsonlib

    from app import training

    source_dir = tmp_path / "src"
    source_dir.mkdir()
    for index in range(20):
        (source_dir / f"ref{index}.png").write_bytes(b"pixels-%d" % index)

    ids = [uuid4() for _ in range(20)]

    class RotatingDb:
        def __init__(self) -> None:
            self.index = 0

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, model, key):
            asset = _asset(object_key=f"src/ref{self.index}.png")
            self.index += 1
            return asset

    monkeypatch.setattr(training, "SessionLocal", RotatingDb)
    monkeypatch.setattr(training.settings, "local_media_dir", str(tmp_path))
    monkeypatch.setattr(training.settings, "storage_enabled", False)
    monkeypatch.setattr(training.storage, "local_root", tmp_path)

    persona = uuid4()
    dataset = training.prepare_dataset(persona, ids, "Petrick", "cinematic realism")

    assert dataset == tmp_path / "datasets" / str(persona)
    manifest = dataset / "metadata.jsonl"
    lines = manifest.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 20
    first = jsonlib.loads(lines[0])
    assert first["file_name"] == "001.png", "names must be zero-padded and ordered"
    assert first["text"] == "photo of Petrick, cinematic realism, identity reference 1"
    assert (dataset / "001.png").read_bytes() == b"pixels-0"
    assert (dataset / "020.png").is_file()


def test_execute_training_refuses_when_disabled(monkeypatch) -> None:
    from app import training

    monkeypatch.setattr(training.settings, "training_enabled", False)
    with pytest.raises(training.TrainingError, match="LoRA training is disabled"):
        training.execute_training(Path("/tmp/ds"), Path("/tmp/out"))


def test_execute_training_refuses_without_a_trainer_command(monkeypatch) -> None:
    from app import training

    monkeypatch.setattr(training.settings, "training_enabled", True)
    monkeypatch.setattr(training.settings, "lora_trainer_command", "")
    with pytest.raises(training.TrainingError, match="BROBOND_LORA_TRAINER_COMMAND is not configured"):
        training.execute_training(Path("/tmp/ds"), Path("/tmp/out"))


def test_execute_training_reports_the_trainer_stderr(monkeypatch, tmp_path) -> None:
    """The operator needs the trainer's own message, not a generic failure."""

    from app import training

    monkeypatch.setattr(training.settings, "training_enabled", True)
    monkeypatch.setattr(training.settings, "lora_trainer_command", "kohya-train --rank 8")
    captured: dict = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        return types.SimpleNamespace(returncode=3, stderr="OOM at step 400")

    monkeypatch.setattr(training.subprocess, "run", fake_run)
    with pytest.raises(training.TrainingError, match="OOM at step 400"):
        training.execute_training(tmp_path / "ds", tmp_path / "out")
    assert captured["command"][:2] == ["kohya-train", "--rank"]
    assert "--dataset" in captured["command"] and "--output" in captured["command"]


def test_execute_training_refuses_a_run_that_produced_no_weights(monkeypatch, tmp_path) -> None:
    """A zero exit code with no safetensors is not a successful training run."""

    from app import training

    monkeypatch.setattr(training.settings, "training_enabled", True)
    monkeypatch.setattr(training.settings, "lora_trainer_command", "kohya-train")
    monkeypatch.setattr(
        training.subprocess,
        "run",
        lambda *a, **k: types.SimpleNamespace(returncode=0, stderr=""),
    )
    with pytest.raises(training.TrainingError, match="without producing a safetensors"):
        training.execute_training(tmp_path / "ds", tmp_path / "out")


def test_execute_training_returns_the_last_weight_file(monkeypatch, tmp_path) -> None:
    from app import training

    monkeypatch.setattr(training.settings, "training_enabled", True)
    monkeypatch.setattr(training.settings, "lora_trainer_command", "kohya-train")
    monkeypatch.setattr(
        training.subprocess,
        "run",
        lambda *a, **k: types.SimpleNamespace(returncode=0, stderr=""),
    )
    output = tmp_path / "out"
    output.mkdir()
    (output / "epoch-001.safetensors").write_bytes(b"a")
    (output / "epoch-002.safetensors").write_bytes(b"b")
    (output / "training.log").write_text("noise")

    assert training.execute_training(tmp_path / "ds", output).name == "epoch-002.safetensors"


def test_execute_training_falls_back_when_stderr_is_empty(monkeypatch, tmp_path) -> None:
    from app import training

    monkeypatch.setattr(training.settings, "training_enabled", True)
    monkeypatch.setattr(training.settings, "lora_trainer_command", "kohya-train")
    monkeypatch.setattr(
        training.subprocess,
        "run",
        lambda *a, **k: types.SimpleNamespace(returncode=1, stderr=""),
    )
    with pytest.raises(training.TrainingError, match="LoRA trainer failed"):
        training.execute_training(tmp_path / "ds", tmp_path / "out")
