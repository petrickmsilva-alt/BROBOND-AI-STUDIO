"""PR008 — Cinematic Render Engine.

Director (`ProductionPlan` / `StoryboardState`) -> `SceneRenderer` ->
`GenerationSpec` -> `GenerationExecutor` -> `RenderAssetPipeline` -> assets
+ jobs, with push-based progress over `/ws/render/{batch_id}`.

Zero provider coupling: the render package may use the executor, never a
provider adapter, brand or catalogue id.
"""

from __future__ import annotations

import asyncio
import builtins
import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from starlette.websockets import WebSocketDisconnect

from app.core.contracts import GenerationKind, GenerationSpec
from app.core.director import DirectorAgent as ProductionDirectorAgent
from app.core.director.production_plan import ProductionPlan
from app.core.director.storyboard_state import StoryboardState
from app.main import app
from app.providers.base_provider import (
    BaseProvider,
    ProviderAsset,
    ProviderCapabilities,
    ProviderEstimate,
    ProviderHealth,
)
from app.providers.generation_executor import GenerationExecutor
from app.providers.mock_provider import MockProvider
from app.providers.provider_registry import ProviderRegistration, ProviderRegistry
from app.render import (
    EVENT_BATCH_COMPLETED,
    EVENT_BATCH_STARTED,
    EVENT_SCENE_COMPLETED,
    EVENT_SCENE_PROGRESS,
    EVENT_SCENE_STARTED,
    RENDER_EVENTS,
    RenderAssetPipeline,
    RenderBatch,
    RenderBatchStatus,
    RenderBatchStore,
    RenderOrchestrator,
    RenderProgressHub,
    RenderScene,
    RenderSceneStatus,
    SceneRenderer,
    SceneRenderInput,
    render_event,
)
from app.render.render_orchestrator import DEFAULT_SEED_BASE, default_persona_phrase

client = TestClient(app)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_storage(tmp_path, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "local_media_dir", str(tmp_path / "media"))
    from app.storage import StorageService

    return StorageService()


@pytest.fixture()
def mock_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register(
        ProviderRegistration(
            provider_id="mock",
            label="Mock",
            factory=lambda model_id=None: MockProvider(),
            default_for=(GenerationKind.IMAGE, GenerationKind.VIDEO),
        )
    )
    return registry


@pytest.fixture()
def harness(tmp_path, tmp_storage, mock_registry) -> SimpleNamespace:
    store = RenderBatchStore()
    hub = RenderProgressHub()
    orchestrator = RenderOrchestrator(
        executor=GenerationExecutor(mock_registry),
        pipeline=RenderAssetPipeline(storage=tmp_storage, staging_dir=tmp_path / "staging"),
        store=store,
        hub=hub,
    )
    return SimpleNamespace(store=store, hub=hub, orchestrator=orchestrator, storage=tmp_storage)


@pytest.fixture()
def plan() -> ProductionPlan:
    return ProductionDirectorAgent().create_production_plan(
        user_intent="luxury watch commercial in a neon city",
        persona_id="CHAR_PETRICK",
        platform="cinema",
        duration=20.0,
    )


def scene_input(scene_number: int = 1, **overrides) -> SceneRenderInput:
    base = {
        "scene_number": scene_number,
        "title": f"Scene {scene_number}",
        "objective": "reveal the hero product in motion",
        "persona": "persona memory CHAR_PETRICK",
        "style": "cinematic realism",
        "mood": "Epic",
        "camera": "tracking shot",
        "lens": "35mm",
        "lighting": "neon practicals",
        "motion": "slow dolly forward",
    }
    base.update(overrides)
    return SceneRenderInput(**base)


def scene_payload(scene_number: int = 1, **overrides) -> dict:
    payload = {
        "scene_number": scene_number,
        "title": f"Scene {scene_number}",
        "objective": "reveal the hero product in motion",
        "camera": "tracking shot",
        "lens": "35mm",
        "lighting": "neon practicals",
        "motion": "slow dolly forward",
        "duration": 5.0,
        "environment": "neon city street",
        "negative_prompt": "",
    }
    payload.update(overrides)
    return payload


def batch_payload(**overrides) -> dict:
    payload = {
        "kind": "image",
        "provider": "mock",
        "project_id": "project-render",
        "style": "cinematic realism",
        "mood": "Epic",
        "aspect_ratio": "16:9",
        "fps": 24,
        "scenes": [scene_payload(1), scene_payload(2)],
    }
    payload.update(overrides)
    return payload


def _register(email: str | None = None) -> tuple[str, dict[str, str]]:
    address = email or f"render-{uuid4()}@example.com"
    response = client.post(
        "/api/v1/auth/register",
        json={"email": address, "name": "Render Owner", "password": "strong-pass-123"},
    )
    assert response.status_code == 201
    token = response.json()["access_token"]
    return token, {"Authorization": f"Bearer {token}"}


class _Reader:
    """One reader thread per socket (same pattern as test_queue_events.py)."""

    def __init__(self, websocket) -> None:
        self.messages: list = []
        self._thread = threading.Thread(target=self._run, args=(websocket,), daemon=True)
        self._thread.start()

    def _run(self, websocket) -> None:
        try:
            while True:
                self.messages.append(websocket.receive_json())
        except Exception:
            pass

    def wait_for(self, predicate, timeout: float = 10.0) -> "_Reader":
        deadline = time.time() + timeout
        while time.time() < deadline and not predicate(self.messages):
            time.sleep(0.05)
        assert predicate(self.messages), f"timed out waiting; got {[m.get('event') for m in self.messages]}"
        return self


# ---------------------------------------------------------------------------
# SceneRenderer
# ---------------------------------------------------------------------------


def test_scene_renderer_builds_a_spec_with_every_mandatory_field() -> None:
    renderer = SceneRenderer()
    spec = renderer.render_spec(
        scene_input(seed=7, aspect_ratio="9:16", duration=10.0),
        kind=GenerationKind.VIDEO,
        provider="mock",
        project_id="project-1",
        user_id="workspace-1",
        persona_id="CHAR_PETRICK",
        fps=30,
    )

    assert isinstance(spec, GenerationSpec)
    assert spec.kind is GenerationKind.VIDEO
    assert spec.provider == "mock"
    assert spec.camera == "tracking shot"
    assert spec.lens == "35mm"
    assert spec.lighting == "neon practicals"
    assert spec.motion == "slow dolly forward"
    assert spec.seed == 7
    assert spec.aspect_ratio == "9:16"
    assert spec.duration == 10.0
    assert spec.fps == 30
    assert spec.project_id == "project-1"
    assert spec.user_id == "workspace-1"
    assert spec.persona_id == "CHAR_PETRICK"


def test_scene_renderer_compiles_through_the_prompt_compiler() -> None:
    renderer = SceneRenderer()
    spec = renderer.render_spec(scene_input())

    # Every mandatory text field lands in the compiled prompt via PromptBlocks.
    for fragment in (
        "reveal the hero product",
        "persona memory CHAR_PETRICK",
        "cinematic realism",
        "Epic",
        "tracking shot",
        "35mm",
        "neon practicals",
        "slow dolly forward",
    ):
        assert fragment in spec.prompt_compiled, fragment
    # The BROBOND quality signature and the negative guard come from the compiler.
    assert "film grain" in spec.prompt_compiled
    assert "plastic skin" in spec.negative_prompt


def test_scene_renderer_is_deterministic() -> None:
    renderer = SceneRenderer()
    first = renderer.render_spec(scene_input(seed=3))
    second = renderer.render_spec(scene_input(seed=3))

    assert first.prompt_compiled == second.prompt_compiled
    assert first.negative_prompt == second.negative_prompt


def test_scene_renderer_accepts_a_kind_string() -> None:
    spec = SceneRenderer().render_spec(scene_input(), kind="video")

    assert spec.kind is GenerationKind.VIDEO


def test_scene_input_adapts_a_director_shot_plan(plan: ProductionPlan) -> None:
    shot = plan.shots[0]
    adapted = SceneRenderInput.from_shot(shot, persona="persona memory CHAR_PETRICK", style=plan.style, mood=plan.mood)

    assert adapted.scene_number == shot.scene_number
    assert adapted.title == shot.title
    assert adapted.objective == shot.objective
    assert adapted.camera == shot.camera
    assert adapted.lens == shot.lens
    assert adapted.lighting == shot.lighting
    assert adapted.motion == shot.motion
    assert adapted.duration == shot.duration
    assert adapted.mood == plan.mood


def test_scene_input_adapts_an_edited_storyboard_scene(plan: ProductionPlan) -> None:
    state = StoryboardState.from_production_plan(plan, project_id="project-1")
    edited = state.apply_mood(state.scenes[0].id, "Dark")
    adapted = SceneRenderInput.from_storyboard_scene(edited.scenes[0], persona="phrase", style="look")

    assert adapted.mood == "Dark"
    assert adapted.title == edited.scenes[0].title
    assert adapted.duration == edited.scenes[0].duration


def test_scene_input_adapts_a_plain_dict() -> None:
    adapted = SceneRenderInput.from_dict(
        {"scene_number": 2, "title": "Turn", "objective": "the turn", "seed": 9, "duration": 7.5}
    )

    assert adapted.scene_number == 2
    assert adapted.seed == 9
    assert adapted.duration == 7.5
    assert adapted.aspect_ratio == "16:9"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"scene_number": 0},
        {"title": "  "},
        {"objective": ""},
        {"duration": 0},
    ],
)
def test_scene_input_rejects_incomplete_scenes(kwargs: dict) -> None:
    base = {"scene_number": 1, "title": "T", "objective": "O"}
    base.update(kwargs)
    with pytest.raises(ValueError):
        SceneRenderInput(**base)


# ---------------------------------------------------------------------------
# RenderBatch
# ---------------------------------------------------------------------------


def make_batch(**overrides) -> RenderBatch:
    scenes = overrides.pop(
        "scenes",
        [
            RenderScene(scene_id="s1", scene_number=1, title="One"),
            RenderScene(scene_id="s2", scene_number=2, title="Two"),
        ],
    )
    payload = {
        "batch_id": "render_test",
        "workspace_id": "workspace-1",
        "project_id": "project-1",
        "kind": "image",
        "provider": "mock",
        "scenes": scenes,
    }
    payload.update(overrides)
    return RenderBatch(**payload)


def test_batch_progress_is_the_mean_of_independent_scene_progresses() -> None:
    batch = make_batch()
    batch.scenes[0].mark_rendering(60)
    batch.scenes[1].mark_rendering(20)

    assert batch.progress == 40
    assert batch.current_scene is batch.scenes[0]
    assert batch.completed_scenes == 0


def test_batch_lifecycle_runs_queued_to_completed() -> None:
    batch = make_batch()
    assert batch.status == RenderBatchStatus.QUEUED.value
    assert not batch.is_terminal
    assert batch.is_cancellable

    batch.mark_running()
    assert batch.status == "running"
    assert batch.started_at
    batch.mark_rendering()
    assert batch.status == "rendering"
    for scene in batch.scenes:
        scene.mark_completed(asset={"object_key": "k"}, job={"id": "j"}, spec_id="spec")
    batch.finish()

    assert batch.status == "completed"
    assert batch.is_terminal
    assert not batch.is_cancellable
    assert batch.progress == 100
    assert batch.current_scene is None
    assert batch.finished_at


def test_batch_finish_marks_failed_when_any_scene_failed() -> None:
    batch = make_batch()
    batch.scenes[0].mark_completed(asset={}, job={}, spec_id="spec")
    batch.scenes[1].mark_failed("gpu exploded")

    batch.finish()

    assert batch.status == "failed"
    assert batch.failed_scenes == 1
    assert batch.is_terminal


def test_batch_finish_marks_cancelled_when_cancel_was_requested() -> None:
    batch = make_batch()
    batch.mark_running()
    assert batch.request_cancel() is True

    batch.finish()

    assert batch.status == "cancelled"


def test_cancel_from_queued_finishes_synchronously() -> None:
    batch = make_batch()

    assert batch.request_cancel() is True
    assert batch.status == "cancelled"
    assert all(scene.status == "cancelled" for scene in batch.scenes)
    assert batch.request_cancel() is False


def test_cancel_marks_only_pending_scenes() -> None:
    batch = make_batch()
    batch.mark_running()
    batch.scenes[0].mark_completed(asset={}, job={}, spec_id="spec")
    batch.scenes[1].mark_running()

    assert batch.request_cancel() is True

    assert batch.scenes[0].status == "completed"
    assert batch.scenes[1].status == "running"
    assert batch.status == "running"


def test_retry_requeues_only_failed_and_cancelled_scenes() -> None:
    batch = make_batch()
    batch.scenes[0].mark_completed(asset={}, job={}, spec_id="spec")
    batch.scenes[1].mark_failed("boom")
    batch.finish()

    reset = batch.reset_for_retry()

    assert reset == 1
    assert batch.status == "queued"
    assert batch.scenes[0].status == "completed"
    assert batch.scenes[1].status == "queued"
    assert batch.scenes[1].progress == 0
    assert batch.scenes[1].error is None


def test_retry_with_nothing_to_retry_keeps_the_batch() -> None:
    batch = make_batch()
    for scene in batch.scenes:
        scene.mark_completed(asset={}, job={}, spec_id="spec")
    batch.finish()

    assert batch.reset_for_retry() == 0
    assert batch.status == "completed"


def test_scene_cancel_is_a_noop_once_terminal() -> None:
    scene = RenderScene(scene_id="s1", scene_number=1, title="One")
    scene.mark_completed(asset={}, job={}, spec_id="spec")
    scene.mark_cancelled()

    assert scene.status == "completed"


def test_batch_serializes_with_aggregates() -> None:
    batch = make_batch()
    payload = batch.to_dict()

    assert payload["progress"] == 0
    assert payload["scene_count"] == 2
    assert payload["current_scene_id"] == "s1"
    assert payload["current_scene_number"] == 1
    assert payload["scenes"][0]["scene_id"] == "s1"
    assert batch.scene("missing") is None
    assert batch.scene("s2") is batch.scenes[1]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"batch_id": "  "},
        {"workspace_id": ""},
        {"kind": "audio"},
        {"scenes": []},
    ],
)
def test_batch_rejects_invalid_batches(kwargs: dict) -> None:
    scenes = [RenderScene(scene_id="s1", scene_number=1, title="One")]
    payload = {
        "batch_id": "b1",
        "workspace_id": "w1",
        "project_id": "p1",
        "kind": "image",
        "provider": "mock",
        "scenes": scenes,
    }
    payload.update(kwargs)
    with pytest.raises(ValueError):
        RenderBatch(**payload)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"scene_id": ""},
        {"scene_number": 0},
        {"title": "  "},
    ],
)
def test_scene_rejects_invalid_rows(kwargs: dict) -> None:
    payload = {"scene_id": "s1", "scene_number": 1, "title": "One"}
    payload.update(kwargs)
    with pytest.raises(ValueError):
        RenderScene(**payload)


def test_store_isolates_workspaces_and_orders_newest_first() -> None:
    store = RenderBatchStore()
    first = make_batch(batch_id="b1", workspace_id="w1", created_at="2026-01-01T00:00:00+00:00")
    second = make_batch(batch_id="b2", workspace_id="w1", created_at="2026-01-02T00:00:00+00:00")
    foreign = make_batch(batch_id="b3", workspace_id="w2")
    store.put(first)
    store.put(second)
    store.put(foreign)

    assert store.get("b1") is first
    assert store.get("missing") is None
    assert store.get_for_workspace("b1", "w1") is first
    assert store.get_for_workspace("b1", "w2") is None
    assert store.get_for_workspace("missing", "w1") is None
    assert [batch.batch_id for batch in store.list_for_workspace("w1")] == ["b2", "b1"]

    store.clear()
    assert store.get("b1") is None


# ---------------------------------------------------------------------------
# Progress engine
# ---------------------------------------------------------------------------


def test_render_events_are_exactly_the_five_contract_names() -> None:
    assert RENDER_EVENTS == (
        "batch_started",
        "scene_started",
        "scene_progress",
        "scene_completed",
        "batch_completed",
    )
    assert EVENT_BATCH_STARTED == "batch_started"
    assert EVENT_SCENE_STARTED == "scene_started"
    assert EVENT_SCENE_PROGRESS == "scene_progress"
    assert EVENT_SCENE_COMPLETED == "scene_completed"
    assert EVENT_BATCH_COMPLETED == "batch_completed"


def test_render_event_carries_only_set_keys() -> None:
    minimal = render_event("b1", "batch_started", status="running", progress=0)
    assert minimal["batch_id"] == "b1"
    assert minimal["event"] == "batch_started"
    assert "scene_id" not in minimal
    assert "error" not in minimal

    full = render_event(
        "b1",
        "scene_completed",
        scene_id="s1",
        scene_number=1,
        status="completed",
        progress=100,
        eta_seconds=2.5,
        error=None,
        asset={"object_key": "k"},
        job={"id": "j"},
    )
    assert full["scene_id"] == "s1"
    assert full["eta_seconds"] == 2.5
    assert full["asset"] == {"object_key": "k"}
    assert "error" not in full

    with pytest.raises(ValueError, match="unknown render event"):
        render_event("b1", "batch_failed")


def test_hub_pushes_to_subscribers_and_replays_history() -> None:
    async def scenario() -> None:
        hub = RenderProgressHub()
        queue = hub.subscribe("b1")
        assert hub.subscriber_count("b1") == 1

        first = render_event("b1", "batch_started", status="running")
        hub.publish("b1", first)
        assert await asyncio.wait_for(queue.get(), timeout=2) is first
        assert hub.history("b1") == [first]
        assert hub.history("b1", after=1) == []

        hub.unsubscribe("b1", queue)
        assert hub.subscriber_count("b1") == 0
        hub.publish("b1", render_event("b1", "batch_completed", status="completed"))
        assert len(hub.history("b1")) == 2

        hub.forget("b1")
        assert hub.history("b1") == []
        hub.clear()

    asyncio.run(scenario())


# ---------------------------------------------------------------------------
# Orchestrator — creation
# ---------------------------------------------------------------------------


def test_orchestrator_builds_a_batch_from_a_production_plan(harness, plan: ProductionPlan) -> None:
    batch = harness.orchestrator.from_production_plan(
        plan, workspace_id="w1", project_id="p1", kind="video", provider="mock", seed=7
    )

    assert batch.workspace_id == "w1"
    assert batch.kind == "video"
    assert batch.provider == "mock"
    assert batch.production_plan_id == plan.id
    assert batch.persona_id == "CHAR_PETRICK"
    assert batch.status == "queued"
    assert batch.scene_count == len(plan.shots)
    assert [scene.title for scene in batch.scenes] == [shot.title for shot in plan.shots]

    inputs = harness.orchestrator.inputs_for(batch.batch_id)
    assert [item.seed for item in inputs] == [7, 8, 9, 10, 11]
    assert all(item.persona == "persona memory CHAR_PETRICK" for item in inputs)
    assert all(item.style == plan.style for item in inputs)
    assert harness.store.get(batch.batch_id) is batch


def test_orchestrator_accepts_a_plan_mapping(harness, plan: ProductionPlan) -> None:
    payload = {
        "id": plan.id,
        "persona_id": None,
        "style": "noir",
        "mood": "Dark",
        "shots": [
            {
                "scene_number": 1,
                "title": "Open",
                "objective": "open on the city",
                "camera": "aerial",
                "lens": "24mm",
                "lighting": "dawn",
                "motion": "drift",
                "duration": 6.0,
                "environment": "rooftops",
                "negative_prompt": "",
            }
        ],
    }
    batch = harness.orchestrator.from_production_plan(payload, workspace_id="w1", project_id="p1")

    assert batch.scene_count == 1
    inputs = harness.orchestrator.inputs_for(batch.batch_id)
    assert inputs[0].persona == "no locked persona"
    assert inputs[0].seed == DEFAULT_SEED_BASE


def test_orchestrator_builds_a_batch_from_an_edited_storyboard(harness, plan: ProductionPlan) -> None:
    state = StoryboardState.from_production_plan(plan, project_id="project-9")
    edited = state.apply_mood(state.scenes[1].id, "Neo")
    batch = harness.orchestrator.from_storyboard_state(
        edited, workspace_id="w1", persona_id="CHAR_PETRICK", style="grade", provider="mock"
    )

    assert batch.project_id == "project-9"
    assert batch.production_plan_id == plan.id
    assert batch.storyboard_version == edited.version
    inputs = harness.orchestrator.inputs_for(batch.batch_id)
    assert inputs[1].mood == "Neo"


def test_orchestrator_accepts_a_storyboard_mapping(harness) -> None:
    payload = {
        "project_id": "pp",
        "production_plan_id": "prod",
        "version": 4,
        "scenes": [
            {
                "scene_number": 1,
                "title": "One",
                "objective": "first",
                "camera": "static",
                "lens": "50mm",
                "lighting": "soft",
                "motion": "still",
                "duration": 5.0,
                "environment": "studio",
                "mood": "Minimal",
                "negative_prompt": "",
            }
        ],
    }
    batch = harness.orchestrator.from_storyboard_state(payload, workspace_id="w1")

    assert batch.storyboard_version == 4
    assert batch.project_id == "pp"


def test_orchestrator_keeps_explicit_scene_seeds(harness) -> None:
    batch = harness.orchestrator.create_batch(
        [scene_input(1, seed=99), scene_input(2)],
        workspace_id="w1",
        project_id="p1",
        seed=7,
    )

    assert [item.seed for item in harness.orchestrator.inputs_for(batch.batch_id)] == [99, 8]


def test_orchestrator_rejects_empty_batches(harness) -> None:
    with pytest.raises(ValueError, match="scenes are required"):
        harness.orchestrator.create_batch([], workspace_id="w1", project_id="p1")


def test_orchestrator_resolves_persona_phrases(harness) -> None:
    assert harness.orchestrator.persona_phrase_for("CHAR_X") == "persona memory CHAR_X"
    assert harness.orchestrator.persona_phrase_for(None) == "no locked persona"
    assert default_persona_phrase("A") == "persona memory A"

    custom = RenderOrchestrator(persona_phrase=lambda pid: f"custom:{pid}")
    assert custom.persona_phrase_for("CHAR_X") == "custom:CHAR_X"


def test_render_package_has_zero_provider_coupling() -> None:
    """The orchestrator is the only provider-facing import; no adapter, brand or catalogue id."""

    banned = (
        "flux_provider",
        "wan_provider",
        "mock_provider",
        "FluxProvider",
        "WanProvider",
        "MockProvider",
        "HunyuanProvider",
        "Hunyuan",
        "Kling",
        "Runway",
        "flux-dev",
        "wan-2.1",
        "hunyuan-video",
    )
    package = Path("backend/app/render")
    offenders: dict[str, list[str]] = {}
    for path in sorted(package.glob("*.py")):
        hits = [token for token in banned if token in path.read_text(encoding="utf-8")]
        if hits:
            offenders[str(path)] = hits
    assert offenders == {}

    orchestrator_source = (package / "render_orchestrator.py").read_text(encoding="utf-8")
    assert "GenerationExecutor" in orchestrator_source
    assert "provider_registry" not in orchestrator_source


# ---------------------------------------------------------------------------
# Orchestrator — run
# ---------------------------------------------------------------------------


def test_run_completes_every_scene_with_assets_and_jobs(harness) -> None:
    batch = harness.orchestrator.create_batch(
        [scene_input(1), scene_input(2)], workspace_id="w1", project_id="p1", provider="mock", seed=7
    )

    result = asyncio.run(harness.orchestrator.run_batch(batch.batch_id))

    assert result is batch
    assert batch.status == "completed"
    assert batch.progress == 100
    assert batch.eta_seconds == 0.0
    for scene in batch.scenes:
        assert scene.status == "completed"
        assert scene.spec_id
        assert scene.job is not None
        assert scene.job["status"] == "complete"
        assert scene.job["provider_id"] == "mock"
        assert scene.asset is not None
        main = harness.storage.local_path(scene.asset["object_key"])
        thumb = harness.storage.local_path(scene.asset["thumbnail_key"])
        metadata_path = harness.storage.local_path(scene.asset["metadata_key"])
        assert main.is_file() and main.suffix == ".png"
        assert thumb.is_file()
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        assert metadata["prompt"] == scene.asset["prompt"]
        assert metadata["seed"] == scene.asset["seed"]
        assert metadata["provider"] == "mock"
    assert [scene.asset["seed"] for scene in batch.scenes] == [7, 8]


def test_run_renders_video_batches_to_mp4(harness) -> None:
    batch = harness.orchestrator.create_batch(
        [scene_input(1)], workspace_id="w1", project_id="p1", kind="video", provider="mock"
    )

    asyncio.run(harness.orchestrator.run_batch(batch.batch_id))

    assert batch.status == "completed"
    asset = batch.scenes[0].asset
    assert asset["kind"] == "video"
    assert harness.storage.local_path(asset["object_key"]).suffix == ".mp4"


def test_run_publishes_the_five_events_in_order(harness) -> None:
    batch = harness.orchestrator.create_batch([scene_input(1)], workspace_id="w1", project_id="p1", provider="mock")

    asyncio.run(harness.orchestrator.run_batch(batch.batch_id))

    kinds = [event["event"] for event in harness.hub.history(batch.batch_id)]
    assert kinds == [
        "batch_started",
        "scene_started",
        "scene_progress",
        "scene_progress",
        "scene_completed",
        "batch_completed",
    ]
    assert all(event["batch_id"] == batch.batch_id for event in harness.hub.history(batch.batch_id))
    terminal = harness.hub.history(batch.batch_id)[-1]
    assert terminal["status"] == "completed"
    assert terminal["progress"] == 100
    assert terminal["eta_seconds"] == 0.0


def test_run_pushes_live_to_subscribers_without_polling(harness) -> None:
    async def scenario() -> None:
        batch = harness.orchestrator.create_batch(
            [scene_input(1)], workspace_id="w1", project_id="p1", provider="mock"
        )
        queue = harness.hub.subscribe(batch.batch_id)
        await harness.orchestrator.run_batch(batch.batch_id)

        received = []
        while not queue.empty():
            received.append(queue.get_nowait()["event"])
        assert received == [
            "batch_started",
            "scene_started",
            "scene_progress",
            "scene_progress",
            "scene_completed",
            "batch_completed",
        ]

    asyncio.run(scenario())


def test_run_continues_after_a_scene_fails(harness, mock_registry) -> None:
    real = GenerationExecutor(mock_registry)

    class FlakyExecutor:
        def execute(self, spec, output_dir, *, provider_id=None, job_id=None):
            if "Two" in spec.prompt_original or spec.prompt_original == "scene two":
                raise RuntimeError("gpu exploded")
            return real.execute(spec, output_dir, provider_id=provider_id, job_id=job_id)

    harness.orchestrator.executor = FlakyExecutor()
    batch = harness.orchestrator.create_batch(
        [scene_input(1, objective="scene one"), scene_input(2, objective="scene two")],
        workspace_id="w1",
        project_id="p1",
        provider="mock",
    )

    asyncio.run(harness.orchestrator.run_batch(batch.batch_id))

    assert batch.status == "failed"
    assert batch.scenes[0].status == "completed"
    assert batch.scenes[1].status == "failed"
    assert batch.scenes[1].error == "gpu exploded"
    failures = [
        event
        for event in harness.hub.history(batch.batch_id)
        if event["event"] == "scene_completed" and event.get("status") == "failed"
    ]
    assert len(failures) == 1
    assert failures[0]["error"] == "gpu exploded"
    assert harness.hub.history(batch.batch_id)[-1]["status"] == "failed"


def test_run_is_idempotent_for_missing_and_started_batches(harness) -> None:
    assert asyncio.run(harness.orchestrator.run_batch("missing")) is None

    batch = harness.orchestrator.create_batch([scene_input(1)], workspace_id="w1", project_id="p1", provider="mock")
    asyncio.run(harness.orchestrator.run_batch(batch.batch_id))
    before = len(harness.hub.history(batch.batch_id))

    again = asyncio.run(harness.orchestrator.run_batch(batch.batch_id))

    assert again is batch
    assert len(harness.hub.history(batch.batch_id)) == before


def test_run_refuses_batches_whose_inputs_are_out_of_sync(harness) -> None:
    batch = harness.orchestrator.create_batch([scene_input(1)], workspace_id="w1", project_id="p1", provider="mock")
    harness.orchestrator._inputs[batch.batch_id] = []

    with pytest.raises(ValueError, match="out of sync"):
        asyncio.run(harness.orchestrator.run_batch(batch.batch_id))


def test_run_marks_pending_scenes_cancelled_when_cancel_lands_mid_run(harness, mock_registry) -> None:
    """Cancel during scene 1: it finishes, scene 2 is cancelled, batch is cancelled."""

    real = GenerationExecutor(mock_registry)
    entered = threading.Event()
    release = threading.Event()

    class GatedExecutor:
        def execute(self, spec, output_dir, *, provider_id=None, job_id=None):
            entered.set()
            assert release.wait(timeout=10), "the test must release the gate"
            return real.execute(spec, output_dir, provider_id=provider_id, job_id=job_id)

    harness.orchestrator.executor = GatedExecutor()
    batch = harness.orchestrator.create_batch(
        [scene_input(1), scene_input(2)], workspace_id="w1", project_id="p1", provider="mock"
    )
    worker = threading.Thread(
        target=lambda: asyncio.run(harness.orchestrator.run_batch(batch.batch_id)), daemon=True
    )
    worker.start()
    try:
        assert entered.wait(timeout=10), "scene 1 never reached the executor"
        cancelled = harness.orchestrator.cancel(batch.batch_id, "w1")
        assert cancelled is batch
        assert batch.status == "rendering"
        release.set()
        worker.join(timeout=15)
        assert not worker.is_alive(), "the run loop did not exit after cancel"
    finally:
        release.set()

    assert batch.status == "cancelled"
    assert batch.scenes[0].status == "completed"
    assert batch.scenes[1].status == "cancelled"
    terminal = harness.hub.history(batch.batch_id)[-1]
    assert terminal["event"] == "batch_completed"
    assert terminal["status"] == "cancelled"
    assert terminal["progress"] == 50


def test_run_skips_scenes_cancelled_before_the_loop_reaches_them(harness) -> None:
    batch = harness.orchestrator.create_batch(
        [scene_input(1), scene_input(2)], workspace_id="w1", project_id="p1", provider="mock"
    )
    batch.scenes[1].mark_cancelled()
    batch.cancel_requested = True

    asyncio.run(harness.orchestrator.run_batch(batch.batch_id))

    assert batch.status == "cancelled"
    assert batch.scenes[0].status == "cancelled"
    assert batch.scenes[1].status == "cancelled"


def test_eta_estimates_remaining_scenes_from_measured_ones(harness) -> None:
    batch = harness.orchestrator.create_batch(
        [scene_input(1), scene_input(2)], workspace_id="w1", project_id="p1", provider="mock"
    )
    assert RenderOrchestrator._eta(batch, []) == 0.0

    batch.scenes[0].mark_completed(asset={}, job={}, spec_id="spec")
    assert RenderOrchestrator._eta(batch, [2.0]) == 2.0

    batch.scenes[1].mark_completed(asset={}, job={}, spec_id="spec")
    assert RenderOrchestrator._eta(batch, [2.0, 2.0]) == 0.0


# ---------------------------------------------------------------------------
# Orchestrator — cancel / retry
# ---------------------------------------------------------------------------


def test_cancel_finishes_a_queued_batch_with_a_terminal_event(harness) -> None:
    batch = harness.orchestrator.create_batch([scene_input(1)], workspace_id="w1", project_id="p1")

    cancelled = harness.orchestrator.cancel(batch.batch_id, "w1")

    assert cancelled is batch
    assert batch.status == "cancelled"
    assert harness.hub.history(batch.batch_id)[-1]["event"] == "batch_completed"
    assert harness.hub.history(batch.batch_id)[-1]["status"] == "cancelled"


def test_cancel_unknown_and_terminal_batches_publishes_nothing(harness) -> None:
    assert harness.orchestrator.cancel("missing", "w1") is None

    batch = harness.orchestrator.create_batch([scene_input(1)], workspace_id="w1", project_id="p1", provider="mock")
    asyncio.run(harness.orchestrator.run_batch(batch.batch_id))
    before = len(harness.hub.history(batch.batch_id))

    again = harness.orchestrator.cancel(batch.batch_id, "w1")

    assert again is batch
    assert len(harness.hub.history(batch.batch_id)) == before


def test_cancel_an_active_batch_leaves_the_terminal_event_to_the_run_loop(harness) -> None:
    batch = harness.orchestrator.create_batch([scene_input(1)], workspace_id="w1", project_id="p1")
    batch.mark_running()

    cancelled = harness.orchestrator.cancel(batch.batch_id, "w1")

    assert cancelled is batch
    assert batch.status == "running"
    assert harness.hub.history(batch.batch_id) == []


def test_retry_reruns_only_failures_to_completed(harness, mock_registry) -> None:
    attempts: list[str] = []
    real = GenerationExecutor(mock_registry)

    class OnceFlakyExecutor:
        def execute(self, spec, output_dir, *, provider_id=None, job_id=None):
            attempts.append(spec.prompt_original)
            if spec.prompt_original == "scene two" and attempts.count("scene two") == 1:
                raise RuntimeError("transient gpu fault")
            return real.execute(spec, output_dir, provider_id=provider_id, job_id=job_id)

    harness.orchestrator.executor = OnceFlakyExecutor()
    batch = harness.orchestrator.create_batch(
        [scene_input(1, objective="scene one"), scene_input(2, objective="scene two")],
        workspace_id="w1",
        project_id="p1",
        provider="mock",
    )
    asyncio.run(harness.orchestrator.run_batch(batch.batch_id))
    assert batch.status == "failed"

    retried, reset = harness.orchestrator.retry(batch.batch_id, "w1")

    assert retried is batch
    assert reset == 1
    assert batch.status == "queued"
    asyncio.run(harness.orchestrator.run_batch(batch.batch_id))
    assert batch.status == "completed"
    assert attempts.count("scene one") == 1
    assert attempts.count("scene two") == 2


def test_retry_refuses_unknown_active_and_complete_batches(harness) -> None:
    assert harness.orchestrator.retry("missing", "w1") == (None, 0)

    batch = harness.orchestrator.create_batch([scene_input(1)], workspace_id="w1", project_id="p1", provider="mock")
    assert harness.orchestrator.retry(batch.batch_id, "w1") == (batch, 0)

    asyncio.run(harness.orchestrator.run_batch(batch.batch_id))
    assert harness.orchestrator.retry(batch.batch_id, "w1") == (batch, 0)

    harness.orchestrator.clear()
    assert harness.orchestrator.inputs_for(batch.batch_id) == ()


# ---------------------------------------------------------------------------
# Asset pipeline
# ---------------------------------------------------------------------------


def _execution(kind: GenerationKind = GenerationKind.IMAGE, seed: int = 7):
    from app.providers.base_provider import ProviderAsset, ProviderEstimate, ProviderJob

    spec = GenerationSpec(
        prompt_original="brief",
        prompt_compiled="compiled cinematic prompt",
        provider="mock",
        kind=kind,
        seed=seed,
    )
    from app.providers.generation_executor import GenerationExecution

    asset = ProviderAsset("/tmp/fake.png", kind.value, "mock", width=64, height=64)
    job = ProviderJob("job-1", "complete", "mock", asset, ProviderEstimate("mock", kind.value, 0.1))
    return GenerationExecution(spec=spec, asset=asset, job=job)


def test_pipeline_persists_main_thumbnail_and_metadata(tmp_path, tmp_storage) -> None:
    source = tmp_path / "rendered.png"
    source.write_bytes(b"fake-image-bytes")
    execution = _execution()
    object.__setattr__(execution.asset, "path", str(source))
    pipeline = RenderAssetPipeline(storage=tmp_storage, staging_dir=tmp_path / "staging")

    asset = pipeline.persist(execution, workspace_id="w1", batch_id="b1", scene_id="s1", scene_number=1)

    assert asset.kind == "image"
    assert asset.prompt == "compiled cinematic prompt"
    assert asset.seed == 7
    assert asset.provider_id == "mock"
    assert "scene-01" in asset.object_key
    assert tmp_storage.local_path(asset.object_key).read_bytes() == b"fake-image-bytes"
    assert tmp_storage.local_path(asset.thumbnail_key).is_file()
    metadata = json.loads(tmp_storage.local_path(asset.metadata_key).read_text(encoding="utf-8"))
    assert metadata["prompt"] == "compiled cinematic prompt"
    assert metadata["seed"] == 7
    assert metadata["provider"] == "mock"
    assert metadata["batch_id"] == "b1"
    assert metadata["scene_number"] == 1
    assert set(asset.to_dict()) >= {"object_key", "thumbnail_url", "metadata_url", "prompt", "seed", "provider_id"}


def test_pipeline_persists_video_as_mp4(tmp_path, tmp_storage) -> None:
    source = tmp_path / "rendered.mp4"
    source.write_bytes(b"fake-video-bytes")
    execution = _execution(kind=GenerationKind.VIDEO)
    object.__setattr__(execution.asset, "path", str(source))
    pipeline = RenderAssetPipeline(storage=tmp_storage)

    asset = pipeline.persist(execution, workspace_id="w1", batch_id="b1", scene_id="s1", scene_number=3)

    assert asset.kind == "video"
    assert tmp_storage.local_path(asset.object_key).suffix == ".mp4"
    assert tmp_storage.local_path(asset.object_key).read_bytes() == b"fake-video-bytes"
    assert tmp_storage.local_path(asset.thumbnail_key).is_file()


def test_pipeline_resizes_real_images_to_thumbnails(tmp_path, tmp_storage) -> None:
    from PIL import Image

    source = tmp_path / "real.png"
    Image.new("RGB", (640, 480), color="red").save(source, format="PNG")
    execution = _execution()
    object.__setattr__(execution.asset, "path", str(source))
    pipeline = RenderAssetPipeline(storage=tmp_storage, staging_dir=tmp_path / "staging")

    asset = pipeline.persist(execution, workspace_id="w1", batch_id="b1", scene_id="s1", scene_number=1)

    with Image.open(tmp_storage.local_path(asset.thumbnail_key)) as thumb:
        assert max(thumb.size) <= 320


def test_pipeline_falls_back_to_a_byte_copy_without_pillow(tmp_path, tmp_storage, monkeypatch) -> None:
    source = tmp_path / "rendered.png"
    source.write_bytes(b"fake-image-bytes")
    execution = _execution()
    object.__setattr__(execution.asset, "path", str(source))

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "PIL" or name.startswith("PIL."):
            raise ImportError("no pillow in this worker")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    pipeline = RenderAssetPipeline(storage=tmp_storage)

    asset = pipeline.persist(execution, workspace_id="w1", batch_id="b1", scene_id="s1", scene_number=1)

    assert tmp_storage.local_path(asset.thumbnail_key).read_bytes() == b"fake-image-bytes"


def test_pipeline_records_asset_rows_when_a_session_is_given(tmp_path, tmp_storage) -> None:
    from app import models  # noqa: F401 — registers the tables
    from app.db import Base

    source = tmp_path / "rendered.png"
    source.write_bytes(b"fake-image-bytes")
    execution = _execution()
    object.__setattr__(execution.asset, "path", str(source))

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        pipeline = RenderAssetPipeline(storage=tmp_storage)
        asset = pipeline.persist(execution, workspace_id="w1", batch_id="b1", scene_id="s1", scene_number=1, db=session)

        rows = session.scalars(select(models.Asset).where(models.Asset.workspace_id == "w1")).all()
        assert {row.object_key for row in rows} == {asset.object_key, asset.thumbnail_key, asset.metadata_key}
        assert {row.kind for row in rows} == {"image", "metadata"}
    finally:
        session.close()
        engine.dispose()


# ---------------------------------------------------------------------------
# HTTP API
# ---------------------------------------------------------------------------


def test_create_batch_returns_201_with_queued_scenes() -> None:
    _, headers = _register()

    response = client.post("/api/v1/render/batches", headers=headers, json=batch_payload(seed=11))

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "queued"
    assert body["progress"] == 0
    assert body["scene_count"] == 2
    assert body["provider"] == "mock"
    assert body["current_scene_number"] == 1
    assert [scene["status"] for scene in body["scenes"]] == ["queued", "queued"]
    assert body["scenes"][0]["asset"] is None
    assert body["scenes"][0]["job"] is None


def test_create_batch_requires_identity_and_valid_scenes() -> None:
    assert client.post("/api/v1/render/batches", json=batch_payload()).status_code == 401

    _, headers = _register()
    assert client.post("/api/v1/render/batches", headers=headers, json=batch_payload(scenes=[])).status_code == 422


def test_list_batches_shows_only_the_caller_queue() -> None:
    _, first = _register()
    _, second = _register()

    client.post("/api/v1/render/batches", headers=first, json=batch_payload())
    client.post("/api/v1/render/batches", headers=first, json=batch_payload(kind="video"))
    client.post("/api/v1/render/batches", headers=second, json=batch_payload())

    assert client.get("/api/v1/render/batches").status_code == 401
    mine = client.get("/api/v1/render/batches", headers=first).json()
    assert len(mine) == 2
    assert {row["kind"] for row in mine} == {"image", "video"}
    assert all(set(row) >= {"batch_id", "status", "progress", "eta_seconds"} for row in mine)
    assert len(client.get("/api/v1/render/batches", headers=second).json()) == 1


def test_batch_detail_is_tenant_scoped() -> None:
    _, headers = _register()
    _, foreign = _register()
    batch_id = client.post("/api/v1/render/batches", headers=headers, json=batch_payload()).json()["batch_id"]

    assert client.get("/api/v1/render/batches/missing", headers=headers).status_code == 404
    assert client.get(f"/api/v1/render/batches/{batch_id}", headers=foreign).status_code == 404
    assert client.get(f"/api/v1/render/batches/{batch_id}").status_code == 401

    body = client.get(f"/api/v1/render/batches/{batch_id}", headers=headers).json()
    assert body["batch_id"] == batch_id
    assert body["scene_count"] == 2


def test_start_renders_the_storyboard_to_completed() -> None:
    _, headers = _register()
    batch_id = client.post("/api/v1/render/batches", headers=headers, json=batch_payload()).json()["batch_id"]

    started = client.post(f"/api/v1/render/batches/{batch_id}/start", headers=headers)

    assert started.status_code == 202
    body = client.get(f"/api/v1/render/batches/{batch_id}", headers=headers).json()
    assert body["status"] == "completed"
    assert body["progress"] == 100
    assert body["eta_seconds"] == 0.0
    assert body["current_scene_id"] is None
    for scene in body["scenes"]:
        assert scene["status"] == "completed"
        assert scene["spec_id"]
        assert scene["asset"]["url"]
        assert scene["asset"]["thumbnail_url"]
        assert scene["asset"]["metadata_url"]
        assert scene["asset"]["provider_id"] == "mock"
        assert scene["job"]["status"] == "complete"


def test_start_refuses_unknown_foreign_and_restarted_batches() -> None:
    _, headers = _register()
    _, foreign = _register()
    batch_id = client.post("/api/v1/render/batches", headers=headers, json=batch_payload()).json()["batch_id"]

    assert client.post("/api/v1/render/batches/missing/start", headers=headers).status_code == 404
    assert client.post(f"/api/v1/render/batches/{batch_id}/start", headers=foreign).status_code == 404
    assert client.post(f"/api/v1/render/batches/{batch_id}/start").status_code == 401

    assert client.post(f"/api/v1/render/batches/{batch_id}/start", headers=headers).status_code == 202
    restarted = client.post(f"/api/v1/render/batches/{batch_id}/start", headers=headers)
    assert restarted.status_code == 409


def test_rendered_assets_land_in_the_workspace_library() -> None:
    _, headers = _register()
    batch_id = client.post("/api/v1/render/batches", headers=headers, json=batch_payload()).json()["batch_id"]
    client.post(f"/api/v1/render/batches/{batch_id}/start", headers=headers)

    assets = client.get("/api/v1/assets", headers=headers).json()

    names = [asset["name"] for asset in assets]
    assert any("scene-01" in name for name in names)
    assert any(name.endswith(".json") for name in names)


def test_cancel_is_idempotent_and_tenant_scoped() -> None:
    _, headers = _register()
    _, foreign = _register()
    batch_id = client.post("/api/v1/render/batches", headers=headers, json=batch_payload()).json()["batch_id"]

    assert client.post(f"/api/v1/render/batches/{batch_id}/cancel").status_code == 401
    assert client.post("/api/v1/render/batches/missing/cancel", headers=headers).status_code == 404
    assert client.post(f"/api/v1/render/batches/{batch_id}/cancel", headers=foreign).status_code == 404

    cancelled = client.post(f"/api/v1/render/batches/{batch_id}/cancel", headers=headers).json()
    assert cancelled["status"] == "cancelled"
    again = client.post(f"/api/v1/render/batches/{batch_id}/cancel", headers=headers).json()
    assert again["status"] == "cancelled"


def test_retry_reruns_failures_and_refuses_anything_else(monkeypatch) -> None:
    from app.providers.mock_provider import MockProvider

    # PR009: a missing/unavailable provider no longer kills a batch — the
    # executor falls back to Mock with the reason recorded. To exercise the
    # failure/retry flow, make the provider fail *fatally* instead: the one
    # error class the fallback chain refuses to mask.
    def explode(self, spec, output_dir):
        raise ValueError("boom: deterministic scene failure for the retry test")

    monkeypatch.setattr(MockProvider, "generate_image", explode)

    _, headers = _register()
    failing = client.post(
        "/api/v1/render/batches", headers=headers, json=batch_payload(provider="mock")
    ).json()["batch_id"]
    client.post(f"/api/v1/render/batches/{failing}/start", headers=headers)
    assert client.get(f"/api/v1/render/batches/{failing}", headers=headers).json()["status"] == "failed"

    retried = client.post(f"/api/v1/render/batches/{failing}/retry", headers=headers)

    assert retried.status_code == 200
    assert retried.json()["retried_scenes"] == 2
    assert "kept" in retried.json()["message"] or "Retrying" in retried.json()["message"]

    # Restore the Mock provider: the rest of the test needs healthy renders.
    monkeypatch.undo()

    completed = client.post("/api/v1/render/batches", headers=headers, json=batch_payload()).json()["batch_id"]
    client.post(f"/api/v1/render/batches/{completed}/start", headers=headers)
    assert client.post(f"/api/v1/render/batches/{completed}/retry", headers=headers).status_code == 409

    queued = client.post("/api/v1/render/batches", headers=headers, json=batch_payload()).json()["batch_id"]
    assert client.post(f"/api/v1/render/batches/{queued}/retry", headers=headers).status_code == 409

    _, foreign = _register()
    assert client.post(f"/api/v1/render/batches/{failing}/retry", headers=foreign).status_code == 404
    assert client.post(f"/api/v1/render/batches/{failing}/retry").status_code == 401
    assert client.post("/api/v1/render/batches/missing/retry", headers=headers).status_code == 404


def test_render_routes_without_a_workspace_see_nothing() -> None:
    from app.db import SessionLocal
    from app.models import Workspace

    _, headers = _register()
    batch_id = client.post("/api/v1/render/batches", headers=headers, json=batch_payload()).json()["batch_id"]
    owner_id = client.get("/api/v1/auth/me", headers=headers).json()["id"]
    with SessionLocal() as db:
        for workspace in db.scalars(select(Workspace).where(Workspace.owner_id == owner_id)).all():
            db.delete(workspace)
        db.commit()

    assert client.get("/api/v1/render/batches", headers=headers).json() == []
    assert client.get(f"/api/v1/render/batches/{batch_id}", headers=headers).status_code == 404
    assert client.post("/api/v1/render/batches", headers=headers, json=batch_payload()).status_code == 404
    assert client.post(f"/api/v1/render/batches/{batch_id}/start", headers=headers).status_code == 404
    assert client.post(f"/api/v1/render/batches/{batch_id}/cancel", headers=headers).status_code == 404
    assert client.post(f"/api/v1/render/batches/{batch_id}/retry", headers=headers).status_code == 404


# ---------------------------------------------------------------------------
# Progress WebSocket
# ---------------------------------------------------------------------------


def test_render_socket_replays_the_full_event_sequence() -> None:
    token, headers = _register()
    batch_id = client.post("/api/v1/render/batches", headers=headers, json=batch_payload()).json()["batch_id"]
    client.post(f"/api/v1/render/batches/{batch_id}/start", headers=headers)

    with client.websocket_connect(f"/ws/render/{batch_id}?token={token}") as websocket:
        reader = _Reader(websocket)
        reader.wait_for(lambda m: any(x.get("event") == "batch_completed" for x in m))

    kinds = [message.get("event") for message in reader.messages]
    assert kinds[0] == "snapshot"
    assert kinds[1:] == [
        "batch_started",
        "scene_started",
        "scene_progress",
        "scene_progress",
        "scene_completed",
        "scene_started",
        "scene_progress",
        "scene_progress",
        "scene_completed",
        "batch_completed",
    ]
    assert reader.messages[0]["batch"]["status"] == "completed"
    assert reader.messages[-1]["status"] == "completed"
    assert reader.messages[-1]["progress"] == 100


def test_render_socket_pushes_live_events_to_an_open_client() -> None:
    from app.main import render_hub, render_store

    token, headers = _register()
    batch_id = client.post("/api/v1/render/batches", headers=headers, json=batch_payload()).json()["batch_id"]

    with client.websocket_connect(f"/ws/render/{batch_id}?token={token}") as websocket:
        reader = _Reader(websocket)
        reader.wait_for(lambda m: any(x.get("event") == "snapshot" for x in m))
        batch = render_store.get(batch_id)
        assert batch is not None
        batch.mark_running()
        render_hub.publish(batch_id, render_event(batch_id, "batch_started", status="running", progress=0))
        reader.wait_for(lambda m: any(x.get("event") == "batch_started" for x in m))
        render_hub.publish(batch_id, render_event(batch_id, "batch_completed", status="cancelled", progress=0))
        reader.wait_for(lambda m: any(x.get("event") == "batch_completed" for x in m))

    kinds = [message.get("event") for message in reader.messages]
    assert kinds == ["snapshot", "batch_started", "batch_completed"]
    assert reader.messages[-1]["status"] == "cancelled"


def test_render_socket_rejects_anonymous_unknown_and_foreign_batches() -> None:
    token, headers = _register()
    _, foreign_headers = _register()
    foreign_token = foreign_headers["Authorization"].split(" ", 1)[1]
    batch_id = client.post("/api/v1/render/batches", headers=headers, json=batch_payload()).json()["batch_id"]

    with pytest.raises(WebSocketDisconnect) as anonymous:
        with client.websocket_connect(f"/ws/render/{batch_id}"):
            pass
    assert anonymous.value.code == 1008

    with pytest.raises(WebSocketDisconnect) as unknown:
        with client.websocket_connect(f"/ws/render/missing?token={token}"):
            pass
    assert unknown.value.code == 1008

    with pytest.raises(WebSocketDisconnect) as foreign:
        with client.websocket_connect(f"/ws/render/{batch_id}?token={foreign_token}"):
            pass
    assert foreign.value.code == 1008


def test_render_socket_unsubscribes_on_disconnect() -> None:
    from app.main import render_hub

    token, headers = _register()
    batch_id = client.post("/api/v1/render/batches", headers=headers, json=batch_payload()).json()["batch_id"]

    with client.websocket_connect(f"/ws/render/{batch_id}?token={token}") as websocket:
        reader = _Reader(websocket)
        reader.wait_for(lambda m: any(x.get("event") == "snapshot" for x in m))
        assert render_hub.subscriber_count(batch_id) == 1

    deadline = time.time() + 5
    while time.time() < deadline and render_hub.subscriber_count(batch_id):
        time.sleep(0.05)
    assert render_hub.subscriber_count(batch_id) == 0


# ---------------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------------


def test_render_studio_page_consumes_the_batch_api_and_push_socket() -> None:
    source = Path("app/studio/render/page.tsx").read_text(encoding="utf-8")

    assert "createRenderBatch(" in source
    assert "startRenderBatch(" in source
    assert "cancelRenderBatch(" in source
    assert "retryRenderBatch(" in source
    assert "wsUrl(`/ws/render/${" in source or 'wsUrl("/ws/render/"' in source
    for label in ("Fila", "Cancelar", "Repetir", "Download", "Preview", "Storyboard"):
        assert label in source, label
    assert "localhost" not in source
    assert "setInterval" not in source


def test_render_api_client_exposes_batches_and_progress() -> None:
    source = Path("lib/api.ts").read_text(encoding="utf-8")

    for function in (
        "createRenderBatch",
        "listRenderBatches",
        "getRenderBatch",
        "startRenderBatch",
        "cancelRenderBatch",
        "retryRenderBatch",
    ):
        assert function in source, function
    assert "/api/v1/render/batches" in source
    assert "RenderBatch" in source


def test_next_proxy_forwards_the_render_socket() -> None:
    config = Path("next.config.mjs").read_text(encoding="utf-8")

    assert "/ws/:path*" in config
    assert "/api/v1/:path*" in config


def test_a_real_png_provider_renders_end_to_end_without_gpu(harness, tmp_path) -> None:
    """A BaseProvider that writes real PNGs flows through executor and pipeline."""

    class PngProvider(BaseProvider):
        provider_id = "png-test"
        label = "Png Test"
        version = "v-test"

        def capabilities(self) -> ProviderCapabilities:
            return ProviderCapabilities("1024", False, True, False, False, True, True)

        def _asset(self, spec: GenerationSpec, output_dir, suffix: str) -> ProviderAsset:
            from PIL import Image

            target = Path(output_dir) / f"{spec.spec_id}.{suffix}"
            target.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (64, 64), color="blue").save(target, format="PNG")
            return ProviderAsset(str(target), "image", self.provider_id, width=64, height=64)

        def generate_image(self, spec: GenerationSpec, output_dir) -> ProviderAsset:
            return self._asset(spec, output_dir, "png")

        def generate_video(self, spec: GenerationSpec, output_dir) -> ProviderAsset:
            raise AssertionError("image batch must not call generate_video")

        def upscale(self, spec: GenerationSpec, asset_path, output_dir) -> ProviderAsset:
            return self._asset(spec, output_dir, "upscaled.png")

        def health(self) -> ProviderHealth:
            return ProviderHealth(self.provider_id, self.label, "ready", 0.0, self.version, self.capabilities())

        def estimate(self, spec: GenerationSpec) -> ProviderEstimate:
            return ProviderEstimate(self.provider_id, spec.kind.value, 0.1)

    registry = ProviderRegistry()
    registry.register(ProviderRegistration("png-test", "Png Test", lambda model_id=None: PngProvider()))
    harness.orchestrator.executor = GenerationExecutor(registry)
    batch = harness.orchestrator.create_batch([scene_input(1)], workspace_id="w1", project_id="p1", provider="png-test")

    asyncio.run(harness.orchestrator.run_batch(batch.batch_id))

    assert batch.status == "completed"
    assert batch.scenes[0].asset["provider_id"] == "png-test"
    assert batch.scenes[0].job["provider_id"] == "png-test"
