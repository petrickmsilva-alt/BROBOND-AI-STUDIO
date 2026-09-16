"""ETAPA 16 tests — the worker's conditioning inputs and the training task.

`queue.py` sat at 60% because the uncovered lines are the ones that need a
database row, an asset on disk, or a Celery broker. None of those are exotic:
they are the paths a real persona-LoRA job takes. This file drives them with a
fake session and real files on a tmp path.
"""
from __future__ import annotations

import types
from pathlib import Path
from uuid import uuid4

import pytest


class FakeSession:
    """A stand-in for `SessionLocal()` that records writes instead of persisting."""

    def __init__(self, rows: dict, log: list) -> None:
        self.rows = rows
        self.log = log
        self.pending: list = []

    def __enter__(self) -> "FakeSession":
        return self

    def __exit__(self, *args) -> bool:
        return False

    def get(self, model, key):
        self.log.append(("get", model.__name__, key))
        return self.rows.get((model.__name__, str(key)))

    def add(self, obj) -> None:
        self.pending.append(obj)
        self.log.append(("add", type(obj).__name__, getattr(obj, "name", "")))

    def flush(self) -> None:
        # SQLAlchemy applies column defaults (`default=lambda: str(uuid4())`)
        # at flush time, not at construction. The task reads `asset.id` right
        # after flushing, so the fake has to behave the same way.
        for obj in self.pending:
            if getattr(obj, "id", None) is None:
                obj.id = str(uuid4())
        self.log.append(("flush",))

    def commit(self) -> None:
        self.log.append(("commit",))


@pytest.fixture()
def db(monkeypatch):
    """Install a fake session factory. Returns `(rows, log)`."""

    from app import queue

    state: dict = {"rows": {}, "log": []}
    monkeypatch.setattr(queue, "SessionLocal", lambda: FakeSession(state["rows"], state["log"]))
    return state["rows"], state["log"]


@pytest.fixture()
def inference(monkeypatch, tmp_path):
    from app.core.config import settings

    monkeypatch.setattr(settings, "inference_enabled", True)
    monkeypatch.setattr(settings, "storage_enabled", False)
    monkeypatch.setattr(settings, "weights_dir", str(tmp_path / "weights"))
    return settings


def _asset(kind: str, workspace_id: str, object_key: str, name: str = "asset", asset_id: str | None = None):
    from app.models import Asset

    return Asset(
        id=asset_id or str(uuid4()),
        workspace_id=workspace_id,
        name=name,
        kind=kind,
        object_key=object_key,
    )


def _job(store_module, parameters: dict | None = None):
    from app.schemas import GenerationType, Job

    return store_module.add_job(
        Job(type=GenerationType.IMAGE, prompt="a red car", parameters=parameters or {})
    )


def _honest_provider(monkeypatch, tmp_path, width: int = 1280, height: int = 720):
    """A provider that writes a real file, so the quality gate has something to read.

    PR009: the seam is the real Flux connector's `generate_image`.
    """

    from app.providers.base_provider import ProviderAsset

    import app.providers.flux_provider as flux_module

    seen: dict = {}

    def honest_generate(self, spec, output_dir):
        seen["spec"] = spec
        target = tmp_path / "render.png"
        target.write_bytes(b"\x89PNG fake")
        return ProviderAsset(
            path=str(target), kind="image", provider_id=self.provider_id, width=width, height=height
        )

    monkeypatch.setattr(flux_module.FluxProvider, "generate_image", honest_generate)
    return seen


# ---------------------------------------------------------------------------
# LoRA conditioning
# ---------------------------------------------------------------------------


def test_a_lora_is_resolved_and_folded_into_the_spec(inference, monkeypatch, db, tmp_path) -> None:
    from app import queue
    from app.storage import storage

    rows, log = db
    workspace = str(uuid4())
    lora_id = str(uuid4())
    rows[("Asset", lora_id)] = _asset("lora", workspace, "loras/persona.safetensors", asset_id=lora_id)

    lora_file = tmp_path / "loras" / "persona.safetensors"
    lora_file.parent.mkdir(parents=True)
    lora_file.write_bytes(b"weights")
    monkeypatch.setattr(storage, "local_root", tmp_path)

    seen = _honest_provider(monkeypatch, tmp_path)
    job = _job(queue.store, {"lora_id": lora_id, "workspace_id": workspace})

    assert queue.process_generation(str(job.id))["status"] == "complete"
    assert seen["spec"].lora == str(lora_file), "the concrete local path must reach the provider"
    assert any(entry[0] == "get" and entry[1] == "Asset" for entry in log)


def test_a_lora_from_another_workspace_is_refused(inference, monkeypatch, db, tmp_path) -> None:
    """Cross-tenant access is the thing this check exists to stop."""

    from app import queue
    from app.storage import storage

    rows, _ = db
    lora_id = str(uuid4())
    rows[("Asset", lora_id)] = _asset("lora", str(uuid4()), "loras/persona.safetensors", asset_id=lora_id)
    monkeypatch.setattr(storage, "local_root", tmp_path)
    _honest_provider(monkeypatch, tmp_path)

    job = _job(queue.store, {"lora_id": lora_id, "workspace_id": str(uuid4())})
    result = queue.process_generation(str(job.id))
    assert result["status"] == "failed"
    assert "not available in this workspace" in result["error"]


def test_a_lora_that_is_not_an_adapter_is_refused(inference, monkeypatch, db, tmp_path) -> None:
    from app import queue
    from app.storage import storage

    rows, _ = db
    workspace = str(uuid4())
    lora_id = str(uuid4())
    rows[("Asset", lora_id)] = _asset("image", workspace, "loras/persona.safetensors", asset_id=lora_id)
    monkeypatch.setattr(storage, "local_root", tmp_path)
    _honest_provider(monkeypatch, tmp_path)

    job = _job(queue.store, {"lora_id": lora_id, "workspace_id": workspace})
    result = queue.process_generation(str(job.id))
    assert result["status"] == "failed"
    assert "not available in this workspace" in result["error"]


def test_a_missing_lora_row_is_refused(inference, monkeypatch, db, tmp_path) -> None:
    from app import queue
    from app.storage import storage

    monkeypatch.setattr(storage, "local_root", tmp_path)
    _honest_provider(monkeypatch, tmp_path)
    job = _job(queue.store, {"lora_id": str(uuid4()), "workspace_id": str(uuid4())})
    result = queue.process_generation(str(job.id))
    assert result["status"] == "failed"
    assert "not available in this workspace" in result["error"]


def test_a_lora_row_pointing_at_nothing_is_refused(inference, monkeypatch, db, tmp_path) -> None:
    """The row can exist while the file behind it does not."""

    from app import queue
    from app.storage import storage

    rows, _ = db
    workspace = str(uuid4())
    lora_id = str(uuid4())
    rows[("Asset", lora_id)] = _asset("lora", workspace, "loras/gone.safetensors", asset_id=lora_id)
    monkeypatch.setattr(storage, "local_root", tmp_path)
    _honest_provider(monkeypatch, tmp_path)

    job = _job(queue.store, {"lora_id": lora_id, "workspace_id": workspace})
    result = queue.process_generation(str(job.id))
    assert result["status"] == "failed"
    assert "adapter file is missing" in result["error"]


def test_a_lora_without_a_workspace_reaches_the_provider_unresolved(inference, monkeypatch, db, tmp_path) -> None:
    """Pins a gap, measured rather than assumed.

    The workspace ownership check only runs when *both* `lora_id` and
    `workspace_id` are present. Without a workspace the requested id is never
    resolved to a file — and `GenerationSpecBuilder` precedence
    (`request.lora > persona.lora_path`) puts that raw string straight into
    `spec.lora`, so the provider receives an asset id where it expects a path.

    It is not a cross-tenant read: no file is opened, so another workspace's
    adapter cannot leak. It is a correctness gap — the model loader gets a
    value it cannot use and fails at load time instead of the worker refusing
    the job earlier. Recorded here so the behaviour is deliberate and visible;
    closing it belongs to a fix etapa, not to this one.
    """

    from app import queue
    from app.storage import storage

    monkeypatch.setattr(storage, "local_root", tmp_path)
    seen = _honest_provider(monkeypatch, tmp_path)
    requested = str(uuid4())
    job = _job(queue.store, {"lora_id": requested})
    assert queue.process_generation(str(job.id))["status"] == "complete"
    assert seen["spec"].lora == requested, (
        "the raw id is passed through unresolved — see the docstring"
    )
    assert not Path(requested).is_absolute()


def test_a_lora_with_a_workspace_is_resolved_to_a_real_path(inference, monkeypatch, db, tmp_path) -> None:
    """The contrast that makes the gap above legible: with a workspace it is a path."""

    from app import queue
    from app.storage import storage

    rows, _ = db
    workspace = str(uuid4())
    lora_id = str(uuid4())
    rows[("Asset", lora_id)] = _asset("lora", workspace, "loras/persona.safetensors", asset_id=lora_id)

    lora_file = tmp_path / "loras" / "persona.safetensors"
    lora_file.parent.mkdir(parents=True)
    lora_file.write_bytes(b"weights")
    monkeypatch.setattr(storage, "local_root", tmp_path)

    seen = _honest_provider(monkeypatch, tmp_path)
    job = _job(queue.store, {"lora_id": lora_id, "workspace_id": workspace})
    assert queue.process_generation(str(job.id))["status"] == "complete"
    assert seen["spec"].lora == str(lora_file)
    assert Path(seen["spec"].lora).is_file()


def test_a_reference_image_is_resolved_and_folded_into_the_spec(inference, monkeypatch, db, tmp_path) -> None:
    from app import queue
    from app.storage import storage

    rows, _ = db
    workspace = str(uuid4())
    reference_id = str(uuid4())
    rows[("Asset", reference_id)] = _asset("image", workspace, "refs/face.png", asset_id=reference_id)

    reference = tmp_path / "refs" / "face.png"
    reference.parent.mkdir(parents=True)
    reference.write_bytes(b"\x89PNG fake")
    monkeypatch.setattr(storage, "local_root", tmp_path)

    seen = _honest_provider(monkeypatch, tmp_path)
    job = _job(queue.store, {"reference_asset_id": reference_id, "workspace_id": workspace})
    assert queue.process_generation(str(job.id))["status"] == "complete"
    assert seen["spec"].reference_path == str(reference)


def test_a_reference_from_another_workspace_is_refused(inference, monkeypatch, db, tmp_path) -> None:
    from app import queue
    from app.storage import storage

    rows, _ = db
    reference_id = str(uuid4())
    rows[("Asset", reference_id)] = _asset("image", str(uuid4()), "refs/face.png", asset_id=reference_id)
    monkeypatch.setattr(storage, "local_root", tmp_path)
    _honest_provider(monkeypatch, tmp_path)

    job = _job(queue.store, {"reference_asset_id": reference_id, "workspace_id": str(uuid4())})
    result = queue.process_generation(str(job.id))
    assert result["status"] == "failed"
    assert "Reference image is not available" in result["error"]


def test_a_video_asset_cannot_be_a_reference_image(inference, monkeypatch, db, tmp_path) -> None:
    from app import queue
    from app.storage import storage

    rows, _ = db
    workspace = str(uuid4())
    reference_id = str(uuid4())
    rows[("Asset", reference_id)] = _asset("video", workspace, "refs/clip.mp4", asset_id=reference_id)
    monkeypatch.setattr(storage, "local_root", tmp_path)
    _honest_provider(monkeypatch, tmp_path)

    job = _job(queue.store, {"reference_asset_id": reference_id, "workspace_id": workspace})
    assert "not available in this workspace" in queue.process_generation(str(job.id))["error"]


def test_a_reference_row_pointing_at_nothing_is_refused(inference, monkeypatch, db, tmp_path) -> None:
    from app import queue
    from app.storage import storage

    rows, _ = db
    workspace = str(uuid4())
    reference_id = str(uuid4())
    rows[("Asset", reference_id)] = _asset("image", workspace, "refs/gone.png", asset_id=reference_id)
    monkeypatch.setattr(storage, "local_root", tmp_path)
    _honest_provider(monkeypatch, tmp_path)

    job = _job(queue.store, {"reference_asset_id": reference_id, "workspace_id": workspace})
    assert "Reference image file is missing" in queue.process_generation(str(job.id))["error"]


# ---------------------------------------------------------------------------
# Persisting into a workspace
# ---------------------------------------------------------------------------


def test_a_job_in_a_workspace_is_saved_as_an_asset(inference, monkeypatch, db, tmp_path) -> None:
    from app import queue
    from app.storage import storage

    rows, log = db
    workspace = str(uuid4())
    monkeypatch.setattr(storage, "local_root", tmp_path)
    _honest_provider(monkeypatch, tmp_path)

    saved: dict = {}

    def fake_save(path, workspace_id, content_type):
        saved.update(path=path, workspace_id=workspace_id, content_type=content_type)
        return f"{workspace_id}/out.png", f"/media/{workspace_id}/out.png"

    monkeypatch.setattr(storage, "save_path", fake_save)

    job = _job(queue.store, {"workspace_id": workspace})
    assert queue.process_generation(str(job.id))["status"] == "complete"

    assert saved["workspace_id"] == workspace
    assert saved["content_type"] == "image/png"
    # PR002: the worker updates the row, so "what the user gets" is read back
    # through the store instead of trusting the pre-process copy.
    job = queue.store.get_job(job.id)
    assert job.output_url == f"/media/{workspace}/out.png", "the workspace URL is what the user gets"
    assert ("add", "Asset", "") in log or any(entry[0] == "add" for entry in log)
    assert ("commit",) in log


def test_a_video_job_is_saved_with_a_video_content_type(inference, monkeypatch, db, tmp_path) -> None:
    from app import queue
    from app.storage import storage
    from app.providers.base_provider import ProviderAsset

    import app.providers.wan_provider as wan_module
    from app.schemas import GenerationType, Job

    monkeypatch.setattr(storage, "local_root", tmp_path)
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"fake")

    def honest_generate(self, spec, output_dir):
        return ProviderAsset(
            path=str(clip),
            kind="video",
            provider_id=self.provider_id,
            duration_seconds=5.0,
            fps=24,
        )

    monkeypatch.setattr(wan_module.WanProvider, "generate_video", honest_generate)

    saved: dict = {}
    monkeypatch.setattr(
        storage,
        "save_path",
        lambda path, workspace_id, content_type: saved.update(content_type=content_type) or (f"{workspace_id}/o.mp4", "/media/o.mp4"),
    )

    workspace = str(uuid4())
    job = queue.store.add_job(Job(type=GenerationType.VIDEO, prompt="x", parameters={"workspace_id": workspace}))
    assert queue.process_generation(str(job.id))["status"] == "complete"
    assert saved["content_type"] == "video/mp4"


def test_a_job_without_a_workspace_keeps_the_local_path(inference, monkeypatch, db, tmp_path) -> None:
    from app import queue
    from app.storage import storage

    monkeypatch.setattr(storage, "local_root", tmp_path)
    _honest_provider(monkeypatch, tmp_path)
    job = _job(queue.store, {})
    assert queue.process_generation(str(job.id))["status"] == "complete"
    # PR002: the worker writes the row, so read the result back through the store.
    job = queue.store.get_job(job.id)
    assert job.output_url == str(tmp_path / "render.png")


# ---------------------------------------------------------------------------
# preprocess_reference task
# ---------------------------------------------------------------------------


def test_preprocess_reference_reports_success(monkeypatch) -> None:
    from app import queue

    monkeypatch.setattr(queue.preprocessor, "preprocess", lambda source, mode, destination: destination)
    result = queue.preprocess_reference("in.png", "edges", "out.png")
    assert result == {"status": "complete", "mode": "edges", "output": "out.png"}


def test_preprocess_reference_reports_failure_without_raising(monkeypatch) -> None:
    """A Celery task that raises is retried forever; the caller needs a verdict."""

    from app import queue

    def boom(source, mode, destination):
        raise RuntimeError("Pillow is required for reference preprocessing")

    monkeypatch.setattr(queue.preprocessor, "preprocess", boom)
    result = queue.preprocess_reference("in.png", "edges", "out.png")
    assert result["status"] == "failed"
    assert "Pillow is required" in result["error"]


def test_preprocess_reference_fails_for_an_unknown_mode() -> None:
    from app import queue

    assert queue.preprocess_reference("in.png", "scribble", "out.png")["status"] == "failed"


# ---------------------------------------------------------------------------
# train_lora task
# ---------------------------------------------------------------------------


@pytest.fixture()
def training_ok(monkeypatch, tmp_path):
    """Make dataset prep and the trainer both succeed."""

    from app import queue

    dataset = tmp_path / "datasets" / "persona"
    dataset.mkdir(parents=True)
    weights = tmp_path / "loras" / "epoch-002.safetensors"
    weights.parent.mkdir(parents=True)
    weights.write_bytes(b"weights")

    seen: dict = {}
    monkeypatch.setattr(queue, "prepare_dataset", lambda *a, **k: (seen.update(prepared=(a, k)), dataset)[1])
    monkeypatch.setattr(queue, "execute_training", lambda ds, out: weights)
    return seen, weights


def test_train_lora_completes_without_a_workspace(inference, monkeypatch, db, training_ok) -> None:
    from app import queue
    from app.models import TrainingRun

    rows, log = db
    run_id = str(uuid4())
    run = TrainingRun(id=run_id, persona_id=str(uuid4()), status="queued", progress=0, log="")
    rows[("TrainingRun", run_id)] = run

    result = queue.train_lora(run_id, str(uuid4()), None, [str(uuid4()) for _ in range(20)], "Petrick", "cinematic realism")

    assert result["status"] == "complete"
    assert result["asset_id"] == "", "no workspace means no asset row"
    assert run.status == "complete" and run.progress == 100
    assert "LoRA adapter created" in run.log
    assert ("commit",) in log


def test_train_lora_registers_the_adapter_as_an_asset(inference, monkeypatch, db, training_ok, tmp_path) -> None:
    from app import queue
    from app.storage import storage
    from app.models import TrainingRun

    rows, log = db
    run_id = str(uuid4())
    workspace = str(uuid4())
    run = TrainingRun(id=run_id, persona_id=str(uuid4()), status="queued", progress=0, log="")
    rows[("TrainingRun", run_id)] = run
    monkeypatch.setattr(storage, "local_root", tmp_path)
    monkeypatch.setattr(storage, "save_path", lambda path, workspace_id, content_type: (f"{workspace_id}/lora.safetensors", "/media/l"))

    result = queue.train_lora(run_id, str(uuid4()), workspace, [str(uuid4()) for _ in range(20)], "Petrick", "cinematic realism")

    assert result["status"] == "complete"
    assert result["asset_id"], "the adapter must be findable afterwards"
    assert ("add", "Asset", "epoch-002.safetensors") in log
    assert run.output_asset_id == result["asset_id"]


def test_train_lora_reports_progress_as_it_goes(inference, monkeypatch, db, training_ok) -> None:
    """The UI shows a percentage; the milestones have to actually be written."""

    from app import queue
    from app.models import TrainingRun

    rows, _ = db
    run_id = str(uuid4())
    rows[("TrainingRun", run_id)] = TrainingRun(id=run_id, persona_id=str(uuid4()), status="queued", progress=0, log="")

    milestones: list = []
    original = queue.SessionLocal

    class Recording(FakeSession):
        def commit(self) -> None:
            run = self.rows.get(("TrainingRun", run_id))
            if run:
                milestones.append((run.status, run.progress, run.log))
            super().commit()

    monkeypatch.setattr(queue, "SessionLocal", lambda: Recording(rows, []))
    queue.train_lora(run_id, str(uuid4()), None, [str(uuid4()) for _ in range(20)], "Petrick", "cinematic realism")

    assert (milestones[0][0], milestones[0][1]) == ("running", 10)
    assert (milestones[1][0], milestones[1][1]) == ("running", 35)
    assert milestones[-1] == ("complete", 100, milestones[-1][2])
    assert original is not None


def test_train_lora_fails_cleanly_when_the_dataset_is_refused(inference, monkeypatch, db) -> None:
    from app import queue
    from app.models import TrainingRun

    rows, _ = db
    run_id = str(uuid4())
    run = TrainingRun(id=run_id, persona_id=str(uuid4()), status="queued", progress=0, log="")
    rows[("TrainingRun", run_id)] = run

    def boom(*args, **kwargs):
        raise RuntimeError("LoRA training requires between 20 and 50 reference assets")

    monkeypatch.setattr(queue, "prepare_dataset", boom)
    result = queue.train_lora(run_id, str(uuid4()), None, [str(uuid4())], "Petrick", "cinematic realism")

    assert result["status"] == "failed"
    assert "between 20 and 50" in result["error"]
    assert run.status == "failed" and run.progress == 100, "a failed run must not be left at 'running'"


def test_train_lora_survives_a_missing_run_row(inference, monkeypatch, db, training_ok) -> None:
    """The run may have been deleted mid-training; the task must still finish."""

    from app import queue

    result = queue.train_lora(str(uuid4()), str(uuid4()), None, [str(uuid4()) for _ in range(20)], "Petrick", "cinematic realism")
    assert result["status"] == "complete"


# ---------------------------------------------------------------------------
# Enqueueing
# ---------------------------------------------------------------------------


def test_enqueue_returns_false_when_the_queue_is_disabled(monkeypatch) -> None:
    from app import queue
    from app.core.config import settings

    monkeypatch.setattr(settings, "queue_enabled", False)
    assert queue.enqueue("job-1") is False


def test_enqueue_submits_when_the_queue_is_enabled(monkeypatch) -> None:
    from app import queue
    from app.core.config import settings

    monkeypatch.setattr(settings, "queue_enabled", True)
    calls: list = []
    monkeypatch.setattr(queue.process_generation, "delay", lambda job_id: calls.append(job_id))
    assert queue.enqueue("job-1") is True
    assert calls == ["job-1"]


def test_enqueue_returns_false_when_the_broker_is_down(monkeypatch) -> None:
    """No Redis must not raise into the request that tried to queue a job."""

    from app import queue
    from app.core.config import settings

    def boom(job_id):
        raise ConnectionError("redis refused")

    monkeypatch.setattr(settings, "queue_enabled", True)
    monkeypatch.setattr(queue.process_generation, "delay", boom)
    assert queue.enqueue("job-1") is False


def test_enqueue_lora_training_returns_false_when_disabled(monkeypatch) -> None:
    from app import queue
    from app.core.config import settings

    monkeypatch.setattr(settings, "queue_enabled", False)
    assert queue.enqueue_lora_training("r", "p", None, [], "i", "s") is False


def test_enqueue_lora_training_submits_when_enabled(monkeypatch) -> None:
    from app import queue
    from app.core.config import settings

    monkeypatch.setattr(settings, "queue_enabled", True)
    calls: list = []
    monkeypatch.setattr(queue.train_lora, "delay", lambda *args: calls.append(args))
    assert queue.enqueue_lora_training("run", "persona", "ws", ["a"], "id", "style") is True
    assert calls == [("run", "persona", "ws", ["a"], "id", "style")]


def test_enqueue_lora_training_returns_false_when_the_broker_is_down(monkeypatch) -> None:
    from app import queue
    from app.core.config import settings

    def boom(*args):
        raise ConnectionError("redis refused")

    monkeypatch.setattr(settings, "queue_enabled", True)
    monkeypatch.setattr(queue.train_lora, "delay", boom)
    assert queue.enqueue_lora_training("r", "p", None, [], "i", "s") is False
