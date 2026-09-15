"""Deterministic prompt composition layer.

Since ETAPA 2 this module is a **facade** over `app.core.PromptCompiler`: the
composition rules live in the Core, and this class only preserves the public
surface the API and the tests already depend on (`PromptEnhancer`,
`default_style`, `enhance(...)`, `prompt_engine`).

Keeping the facade means no route, test or caller had to change when the logic
moved into the Core.
"""
from dataclasses import dataclass, field

from .core.contracts import CompiledPrompt, SceneBeat
from .core.prompt_compiler import PromptCompiler


@dataclass
class PromptEnhancer:
    default_style: str = "cinematic realism"
    compiler: PromptCompiler = field(default_factory=PromptCompiler)

    def __post_init__(self) -> None:
        # Keep the facade's default and the compiler's default in sync, so
        # `PromptEnhancer(default_style=...)` still means what it used to.
        self.compiler.default_style = self.default_style

    def enhance(
        self,
        prompt: str,
        style: str | None = None,
        persona: str | None = None,
        camera: str | None = None,
        lighting: str | None = None,
    ) -> str:
        """Backward-compatible single-string enhancement."""

        return self.compiler.enhance(prompt, style=style, persona=persona, camera=camera, lighting=lighting)

    def compile(
        self,
        prompt: str,
        style: str | None = None,
        persona: str | None = None,
        camera: str | None = None,
        lighting: str | None = None,
        continuity: str | None = None,
        motion: str | None = None,
        lens: str | None = None,
        negative_prompt: str = "",
    ) -> CompiledPrompt:
        """Full compilation, exposing the negative prompt and the token list."""

        return self.compiler.build(
            prompt,
            style=style,
            persona=persona,
            camera=camera,
            lighting=lighting,
            continuity=continuity,
            motion=motion,
            lens=lens,
            negative_prompt=negative_prompt,
        )

    def compose_scene_prompt(
        self,
        brief: str,
        beat: SceneBeat,
        *,
        persona: str | None = None,
        style: str | None = None,
        scene_count: int | None = None,
    ) -> str:
        """Compile one directed beat into its render-ready prompt.

        The storyboard route calls this instead of assembling prompt text
        itself, so no composition logic remains in the HTTP layer.
        """

        total = scene_count if scene_count is not None else beat.number
        return self.compiler.enhance(
            brief,
            style=style,
            persona=persona,
            camera=beat.camera,
            lighting=beat.lighting,
            motion=beat.motion,
            continuity=f"continuity beat {beat.number} of {total}",
        )


prompt_engine = PromptEnhancer()
