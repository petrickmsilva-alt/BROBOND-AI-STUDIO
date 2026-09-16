"""PR008 — RenderOrchestrator: ProductionPlan -> Assets + Jobs (ETAPA 1).

```text
ProductionPlan / StoryboardState
  -> SceneRenderInput (one per scene)
  -> SceneRenderer (+ PromptCompiler) -> GenerationSpec
  -> GenerationExecutor -> ProviderAsset + ProviderJob
  -> RenderAssetPipeline -> PNG/MP4 + thumbnail + metadata
  -> RenderScene records asset + job
```

The orchestrator never calls a provider directly: execution goes only
through `GenerationExecutor`, which resolves providers via the registry
(PR007). Provider ids travel as opaque strings on the batch and the spec.

Batches run scene by scene, in order. One scene failing does not stop its
siblings — the batch finishes `failed` and the Queue UI retries only the
failures. Cancellation is cooperative: the running scene finishes, the rest
are marked cancelled.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Mapping
from dataclasses import replace
from typing import Any

from ..core.contracts import GenerationKind
from ..providers.generation_executor import GenerationExecutor
from .asset_pipeline import RenderAssetPipeline
from .progress import (
    EVENT_BATCH_COMPLETED,
    EVENT_BATCH_STARTED,
    EVENT_SCENE_COMPLETED,
    EVENT_SCENE_PROGRESS,
    EVENT_SCENE_STARTED,
    RenderProgressHub,
    render_event,
    render_hub,
)
from .render_batch import (
    PROGRESS_COMPLETE,
    PROGRESS_QUEUED,
    RenderBatch,
    RenderBatchStatus,
    RenderBatchStore,
    RenderScene,
    RenderSceneStatus,
    render_store,
)
from .scene_renderer import DEFAULT_FPS, SceneRenderer, SceneRenderInput

#: Seed base when the caller passes none. Deterministic on purpose: the same
#: batch re-created renders the same seeds, so a seed means something.
DEFAULT_SEED_BASE = 42000

#: Progress milestones inside one scene (the queue uses the same idea).
PROGRESS_SPEC_COMPILED = 25
PROGRESS_ASSET_PERSISTED = 75

NO_ETA = 0.0


def default_persona_phrase(persona_id: str | None) -> str:
    """Director-compatible fallback when no resolver is injected."""

    return f"persona memory {persona_id}" if persona_id else "no locked persona"


def _field(source: Any, name: str, default: Any = None) -> Any:
    if isinstance(source, Mapping):
        return source.get(name, default)
    return getattr(source, name, default)


class RenderOrchestrator:
    """Builds batches from Director plans and runs them through the executor."""

    def __init__(
        self,
        *,
        executor: GenerationExecutor | None = None,
        scene_renderer: SceneRenderer | None = None,
        pipeline: RenderAssetPipeline | None = None,
        store: RenderBatchStore | None = None,
        hub: RenderProgressHub | None = None,
        persona_phrase: Callable[[str | None], str] | None = None,
    ) -> None:
        self.executor = executor or GenerationExecutor()
        self.scene_renderer = scene_renderer or SceneRenderer()
        self.pipeline = pipeline or RenderAssetPipeline()
        self.store = store or render_store
        self.hub = hub or render_hub
        self._persona_phrase = persona_phrase or default_persona_phrase
        # Scene inputs per batch, aligned with `batch.scenes` by index.
        self._inputs: dict[str, list[SceneRenderInput]] = {}

    # ------------------------------------------------------------- creation

    def from_production_plan(
        self,
        plan: Any,
        *,
        workspace_id: str,
        project_id: str,
        kind: GenerationKind | str = GenerationKind.IMAGE,
        provider: str = "",
        aspect_ratio: str = "16:9",
        fps: int = DEFAULT_FPS,
        seed: int | None = None,
    ) -> RenderBatch:
        """Create a batch from a PR005 `ProductionPlan` (object or mapping)."""

        shots = _field(plan, "shots", ()) or ()
        persona_id = _field(plan, "persona_id")
        style = _field(plan, "style", "") or ""
        mood = _field(plan, "mood", "") or ""
        phrase = self._persona_phrase(persona_id)
        inputs = [
            SceneRenderInput.from_shot(
                shot, persona=phrase, style=style, mood=mood, aspect_ratio=aspect_ratio
            )
            for shot in shots
        ]
        return self.create_batch(
            inputs,
            workspace_id=workspace_id,
            project_id=project_id,
            kind=kind,
            provider=provider,
            production_plan_id=_field(plan, "id"),
            persona_id=persona_id,
            style=style,
            aspect_ratio=aspect_ratio,
            fps=fps,
            seed=seed,
        )

    def from_storyboard_state(
        self,
        state: Any,
        *,
        workspace_id: str,
        project_id: str | None = None,
        persona_id: str | None = None,
        kind: GenerationKind | str = GenerationKind.IMAGE,
        provider: str = "",
        style: str = "",
        aspect_ratio: str = "16:9",
        fps: int = DEFAULT_FPS,
        seed: int | None = None,
    ) -> RenderBatch:
        """Create a batch from a PR006 `StoryboardState` (object or mapping)."""

        scenes = _field(state, "scenes", ()) or ()
        phrase = self._persona_phrase(persona_id)
        inputs = [
            SceneRenderInput.from_storyboard_scene(
                scene, persona=phrase, style=style, aspect_ratio=aspect_ratio
            )
            for scene in scenes
        ]
        return self.create_batch(
            inputs,
            workspace_id=workspace_id,
            project_id=project_id or _field(state, "project_id", "") or "",
            kind=kind,
            provider=provider,
            production_plan_id=_field(state, "production_plan_id"),
            storyboard_version=_field(state, "version"),
            persona_id=persona_id,
            style=style,
            aspect_ratio=aspect_ratio,
            fps=fps,
            seed=seed,
        )

    def create_batch(
        self,
        inputs: list[SceneRenderInput],
        *,
        workspace_id: str,
        project_id: str,
        kind: GenerationKind | str = GenerationKind.IMAGE,
        provider: str = "",
        production_plan_id: str | None = None,
        storyboard_version: int | None = None,
        persona_id: str | None = None,
        style: str = "",
        aspect_ratio: str = "16:9",
        fps: int = DEFAULT_FPS,
        seed: int | None = None,
    ) -> RenderBatch:
        """Create and store a batch. Scenes without a seed get base + index."""

        if not inputs:
            raise ValueError("scenes are required")
        resolved_kind = kind if isinstance(kind, GenerationKind) else GenerationKind(str(kind))
        base = DEFAULT_SEED_BASE if seed is None else int(seed)
        resolved = [
            item if item.seed is not None else replace(item, seed=base + index)
            for index, item in enumerate(inputs)
        ]
        batch_id = self.store.new_id()
        scenes = [
            RenderScene(
                scene_id=f"{batch_id}-s{item.scene_number:02d}",
                scene_number=item.scene_number,
                title=item.title,
            )
            for item in resolved
        ]
        batch = RenderBatch(
            batch_id=batch_id,
            workspace_id=workspace_id,
            project_id=project_id or "default-project",
            kind=resolved_kind.value,
            provider=provider or "",
            scenes=scenes,
            production_plan_id=production_plan_id,
            storyboard_version=storyboard_version,
            persona_id=persona_id,
            style=style or "",
            aspect_ratio=aspect_ratio,
            fps=int(fps),
            seed=seed,
        )
        self._inputs[batch_id] = resolved
        return self.store.put(batch)

    def inputs_for(self, batch_id: str) -> tuple[SceneRenderInput, ...]:
        return tuple(self._inputs.get(batch_id, ()))

    def persona_phrase_for(self, persona_id: str | None) -> str:
        """Resolve a persona id to its prompt phrase (injected resolver)."""

        return self._persona_phrase(persona_id)

    # ------------------------------------------------------------------ run

    async def run_batch(self, batch_id: str, *, db_session_factory: Callable[[], Any] | None = None) -> RenderBatch | None:
        """Run every non-terminal scene through spec -> executor -> pipeline."""

        batch = self.store.get(batch_id)
        if batch is None or batch.status != RenderBatchStatus.QUEUED.value:
            return batch
        inputs = self._inputs.get(batch_id, [])
        if len(inputs) != len(batch.scenes):
            raise ValueError("scene inputs are out of sync with the batch")

        batch.mark_running()
        self.hub.publish(
            batch_id,
            render_event(batch_id, EVENT_BATCH_STARTED, status=batch.status, progress=batch.progress),
        )

        output_dir = self.pipeline.storage.local_root / batch.workspace_id / "renders" / batch_id
        output_dir.mkdir(parents=True, exist_ok=True)
        db = db_session_factory() if db_session_factory is not None else None
        try:
            await self._render_scenes(batch, inputs, output_dir, db)
        finally:
            if db is not None:
                db.close()

        batch.finish()
        self.hub.publish(
            batch_id,
            render_event(
                batch_id,
                EVENT_BATCH_COMPLETED,
                status=batch.status,
                progress=batch.progress,
                eta_seconds=batch.eta_seconds,
            ),
        )
        return batch

    async def _render_scenes(
        self, batch: RenderBatch, inputs: list[SceneRenderInput], output_dir: Any, db: Any
    ) -> None:
        elapsed: list[float] = []
        for index, scene in enumerate(batch.scenes):
            if scene.is_terminal:
                continue
            if batch.cancel_requested:
                scene.mark_cancelled()
                continue
            await self._render_scene(batch, scene, inputs[index], output_dir, db, elapsed)

    async def _render_scene(
        self,
        batch: RenderBatch,
        scene: RenderScene,
        render_input: SceneRenderInput,
        output_dir: Any,
        db: Any,
        elapsed: list[float],
    ) -> None:
        scene.mark_running()
        batch.mark_rendering()
        self.hub.publish(
            batch.batch_id,
            render_event(
                batch.batch_id,
                EVENT_SCENE_STARTED,
                scene_id=scene.scene_id,
                scene_number=scene.scene_number,
                status=scene.status,
                progress=PROGRESS_QUEUED,
                eta_seconds=batch.eta_seconds,
            ),
        )
        started = time.perf_counter()
        try:
            spec = self.scene_renderer.render_spec(
                render_input,
                kind=batch.kind,
                provider=batch.provider,
                project_id=batch.project_id,
                user_id=batch.workspace_id,
                persona_id=batch.persona_id,
                fps=batch.fps,
            )
            self.hub.publish(
                batch.batch_id,
                render_event(
                    batch.batch_id,
                    EVENT_SCENE_PROGRESS,
                    scene_id=scene.scene_id,
                    scene_number=scene.scene_number,
                    status=RenderSceneStatus.RENDERING.value,
                    progress=PROGRESS_SPEC_COMPILED,
                    eta_seconds=batch.eta_seconds,
                ),
            )
            scene.mark_rendering(PROGRESS_SPEC_COMPILED)
            # Providers are synchronous and GPU-bound: never block the loop.
            execution = await asyncio.to_thread(
                self.executor.execute,
                spec,
                output_dir,
                provider_id=batch.provider or None,
                job_id=f"{batch.batch_id}-s{scene.scene_number:02d}",
            )
            asset = self.pipeline.persist(
                execution,
                workspace_id=batch.workspace_id,
                batch_id=batch.batch_id,
                scene_id=scene.scene_id,
                scene_number=scene.scene_number,
                db=db,
            )
            scene.mark_rendering(PROGRESS_ASSET_PERSISTED)
            self.hub.publish(
                batch.batch_id,
                render_event(
                    batch.batch_id,
                    EVENT_SCENE_PROGRESS,
                    scene_id=scene.scene_id,
                    scene_number=scene.scene_number,
                    status=RenderSceneStatus.RENDERING.value,
                    progress=PROGRESS_ASSET_PERSISTED,
                    eta_seconds=batch.eta_seconds,
                ),
            )
            scene.mark_completed(asset=asset.to_dict(), job=execution.job.to_dict(), spec_id=spec.spec_id)
        except Exception as error:
            scene.mark_failed(str(error) or "render failed")
            self.hub.publish(
                batch.batch_id,
                render_event(
                    batch.batch_id,
                    EVENT_SCENE_COMPLETED,
                    scene_id=scene.scene_id,
                    scene_number=scene.scene_number,
                    status=scene.status,
                    progress=scene.progress,
                    eta_seconds=self._eta(batch, elapsed),
                    error=scene.error,
                ),
            )
            return

        elapsed.append(time.perf_counter() - started)
        batch.eta_seconds = self._eta(batch, elapsed)
        self.hub.publish(
            batch.batch_id,
            render_event(
                batch.batch_id,
                EVENT_SCENE_COMPLETED,
                scene_id=scene.scene_id,
                scene_number=scene.scene_number,
                status=scene.status,
                progress=PROGRESS_COMPLETE,
                eta_seconds=batch.eta_seconds,
                asset=scene.asset,  # type: ignore[arg-type]
                job=scene.job,  # type: ignore[arg-type]
            ),
        )

    @staticmethod
    def _eta(batch: RenderBatch, elapsed: list[float]) -> float:
        remaining = sum(1 for scene in batch.scenes if not scene.is_terminal)
        if not remaining or not elapsed:
            return NO_ETA
        return round((sum(elapsed) / len(elapsed)) * remaining, 2)

    # -------------------------------------------------------- cancel / retry

    def cancel(self, batch_id: str, workspace_id: str) -> RenderBatch | None:
        """Request cancellation. A queued batch finishes synchronously."""

        batch = self.store.get_for_workspace(batch_id, workspace_id)
        if batch is None or not batch.request_cancel():
            return batch
        if batch.is_terminal:
            self.hub.publish(
                batch_id,
                render_event(
                    batch_id,
                    EVENT_BATCH_COMPLETED,
                    status=batch.status,
                    progress=batch.progress,
                    eta_seconds=batch.eta_seconds,
                ),
            )
        return batch

    def retry(self, batch_id: str, workspace_id: str) -> tuple[RenderBatch | None, int]:
        """Re-queue failed/cancelled scenes. Active batches cannot retry."""

        batch = self.store.get_for_workspace(batch_id, workspace_id)
        if batch is None or not batch.is_terminal:
            return batch, 0
        reset = batch.reset_for_retry()
        return batch, reset

    def clear(self) -> None:
        """Test-only reset of the per-batch scene inputs."""

        self._inputs.clear()
