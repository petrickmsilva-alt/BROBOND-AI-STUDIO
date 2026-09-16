"""PR008 — SceneRenderer: one storyboard scene becomes one GenerationSpec.

Each scene carries the mandatory render fields (ETAPA 2):

```text
persona, style, mood, camera, lens, lighting, motion, seed, aspect_ratio, duration
```

Prompt text is produced only through the existing `PromptCompiler` — the
renderer assembles `PromptBlocks` and compiles, exactly like the Director
does for planning. The renderer never invents identity: `persona` arrives as
an already-resolved phrase (the orchestrator resolves `persona_id` first).

Input sources, in product order:

1. `StoryboardScene` (PR006) — the edited visual plan;
2. `ShotPlan` (PR005) — the Director plan, unedited;
3. plain dicts — the API payload, which carries the plan inline because
   production plans are not persisted server-side.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..core.contracts import GenerationKind, GenerationSpec, PromptBlocks
from ..core.prompt_compiler import PromptCompiler

DEFAULT_FPS = 24
DEFAULT_DURATION_SECONDS = 5.0
DEFAULT_ASPECT_RATIO = "16:9"


def _get(source: Any, name: str, default: Any = "") -> Any:
    """Read a field from a plan object or an equivalent mapping."""

    if isinstance(source, Mapping):
        return source.get(name, default)
    return getattr(source, name, default)


@dataclass(frozen=True)
class SceneRenderInput:
    """The mandatory per-scene render contract."""

    scene_number: int
    title: str
    objective: str
    persona: str = ""
    style: str = ""
    mood: str = ""
    camera: str = ""
    lens: str = ""
    lighting: str = ""
    motion: str = ""
    environment: str = ""
    negative_prompt: str = ""
    seed: int | None = None
    aspect_ratio: str = DEFAULT_ASPECT_RATIO
    duration: float = DEFAULT_DURATION_SECONDS

    def __post_init__(self) -> None:
        if self.scene_number < 1:
            raise ValueError("scene_number must be positive")
        if not self.title.strip():
            raise ValueError("title is required")
        if not self.objective.strip():
            raise ValueError("objective is required")
        if self.duration <= 0:
            raise ValueError("duration must be positive")

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SceneRenderInput":
        data = dict(payload)
        return cls(
            scene_number=int(data.get("scene_number", 0)),
            title=str(data.get("title", "")),
            objective=str(data.get("objective", "")),
            persona=str(data.get("persona", "") or ""),
            style=str(data.get("style", "") or ""),
            mood=str(data.get("mood", "") or ""),
            camera=str(data.get("camera", "") or ""),
            lens=str(data.get("lens", "") or ""),
            lighting=str(data.get("lighting", "") or ""),
            motion=str(data.get("motion", "") or ""),
            environment=str(data.get("environment", "") or ""),
            negative_prompt=str(data.get("negative_prompt", "") or ""),
            seed=data.get("seed"),
            aspect_ratio=str(data.get("aspect_ratio", DEFAULT_ASPECT_RATIO) or DEFAULT_ASPECT_RATIO),
            duration=float(data.get("duration", DEFAULT_DURATION_SECONDS)),
        )

    @classmethod
    def from_shot(
        cls,
        shot: Any,
        *,
        persona: str = "",
        style: str = "",
        mood: str = "",
        seed: int | None = None,
        aspect_ratio: str = DEFAULT_ASPECT_RATIO,
    ) -> "SceneRenderInput":
        """Adapt a PR005 `ShotPlan` (object or mapping with the same fields)."""

        return cls(
            scene_number=int(_get(shot, "scene_number", 0)),
            title=str(_get(shot, "title")),
            objective=str(_get(shot, "objective")),
            persona=persona,
            style=style or str(_get(shot, "style", "")),
            mood=mood,
            camera=str(_get(shot, "camera")),
            lens=str(_get(shot, "lens")),
            lighting=str(_get(shot, "lighting")),
            motion=str(_get(shot, "motion")),
            environment=str(_get(shot, "environment")),
            negative_prompt=str(_get(shot, "negative_prompt")),
            seed=seed,
            aspect_ratio=aspect_ratio,
            duration=float(_get(shot, "duration", DEFAULT_DURATION_SECONDS)),
        )

    @classmethod
    def from_storyboard_scene(
        cls,
        scene: Any,
        *,
        persona: str = "",
        style: str = "",
        seed: int | None = None,
        aspect_ratio: str = DEFAULT_ASPECT_RATIO,
    ) -> "SceneRenderInput":
        """Adapt a PR006 `StoryboardScene`, keeping the editor's mood per scene."""

        return cls(
            scene_number=int(_get(scene, "scene_number", 0)),
            title=str(_get(scene, "title")),
            objective=str(_get(scene, "objective")),
            persona=persona,
            style=style,
            mood=str(_get(scene, "mood", "")),
            camera=str(_get(scene, "camera")),
            lens=str(_get(scene, "lens")),
            lighting=str(_get(scene, "lighting")),
            motion=str(_get(scene, "motion")),
            environment=str(_get(scene, "environment")),
            negative_prompt=str(_get(scene, "negative_prompt")),
            seed=seed,
            aspect_ratio=aspect_ratio,
            duration=float(_get(scene, "duration", DEFAULT_DURATION_SECONDS)),
        )


class SceneRenderer:
    """Compiles scene inputs into executable `GenerationSpec` objects."""

    def __init__(self, compiler: PromptCompiler | None = None) -> None:
        self.compiler = compiler or PromptCompiler()

    def render_spec(
        self,
        scene: SceneRenderInput,
        *,
        kind: GenerationKind | str = GenerationKind.IMAGE,
        provider: str = "",
        project_id: str | None = None,
        user_id: str | None = None,
        persona_id: str | None = None,
        fps: int = DEFAULT_FPS,
    ) -> GenerationSpec:
        """Compile one scene into the single object a provider receives.

        `mood` has no dedicated prompt block, so it rides COLOR (the grade the
        mood implies) and CONTINUITY (the mood must hold across the sequence).
        Both placements are explicit in the compiled prompt, never silent.
        """

        resolved_kind = kind if isinstance(kind, GenerationKind) else GenerationKind(str(kind))
        compiled = self.compiler.compile(
            PromptBlocks(
                subject=self.compiler.normalize(scene.objective),
                persona=self.compiler.normalize(scene.persona),
                environment=self.compiler.normalize(scene.environment),
                action=self.compiler.normalize(scene.title),
                camera=self.compiler.normalize(scene.camera),
                lens=self.compiler.normalize(scene.lens),
                light=self.compiler.normalize(scene.lighting),
                color=self.compiler.normalize(scene.mood),
                motion=self.compiler.normalize(scene.motion),
                style=self.compiler.normalize(scene.style),
                continuity=self.compiler.normalize(f"scene {scene.scene_number} {scene.title} continuity"),
                output=self.compiler.output_block,
                negative=scene.negative_prompt,
            )
        )
        return GenerationSpec(
            prompt_original=scene.objective,
            prompt_compiled=compiled.prompt,
            project_id=project_id,
            user_id=user_id,
            persona_id=persona_id,
            negative_prompt=compiled.negative_prompt,
            camera=scene.camera,
            lens=scene.lens,
            lighting=scene.lighting,
            motion=scene.motion,
            aspect_ratio=scene.aspect_ratio,
            fps=int(fps),
            duration=float(scene.duration),
            provider=provider,
            seed=scene.seed,
            kind=resolved_kind,
        )
