"""PR008 — Cinematic Render Engine.

Connects the Director AI (`ProductionPlan` / `StoryboardState`) to the
`GenerationExecutor` so storyboards produce real images and videos.

Flow (ETAPA 1):

```text
ProductionPlan
  -> Scene (SceneRenderer + PromptCompiler)
  -> GenerationSpec
  -> GenerationExecutor (Registry -> Provider)
  -> ProviderAsset -> RenderAssetPipeline -> stored files
  -> ProviderJob recorded per scene
```

Zero provider coupling: nothing in this package imports a provider adapter,
a provider brand or a catalogue id. The only provider-facing dependency is
`GenerationExecutor`, which is provider-agnostic by construction (PR007).
"""

from .asset_pipeline import RenderAsset, RenderAssetPipeline
from .progress import (
    EVENT_BATCH_COMPLETED,
    EVENT_BATCH_STARTED,
    EVENT_SCENE_COMPLETED,
    EVENT_SCENE_PROGRESS,
    EVENT_SCENE_STARTED,
    RENDER_EVENTS,
    RenderProgressHub,
    render_event,
    render_hub,
)
from .render_batch import (
    RenderBatch,
    RenderBatchStatus,
    RenderBatchStore,
    RenderScene,
    RenderSceneStatus,
    render_store,
)
from .render_orchestrator import RenderOrchestrator
from .scene_renderer import SceneRenderer, SceneRenderInput

__all__ = [
    "EVENT_BATCH_COMPLETED",
    "EVENT_BATCH_STARTED",
    "EVENT_SCENE_COMPLETED",
    "EVENT_SCENE_PROGRESS",
    "EVENT_SCENE_STARTED",
    "RENDER_EVENTS",
    "RenderAsset",
    "RenderAssetPipeline",
    "RenderBatch",
    "RenderBatchStatus",
    "RenderBatchStore",
    "RenderOrchestrator",
    "RenderProgressHub",
    "RenderScene",
    "RenderSceneStatus",
    "SceneRenderer",
    "SceneRenderInput",
    "render_event",
    "render_hub",
    "render_store",
]
