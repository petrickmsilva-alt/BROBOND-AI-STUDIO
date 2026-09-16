"""GenerationSpecBuilder — the composition root of BROBOND CORE.

Responsibility: combine persona memory, style, shot and intent into a single
`GenerationSpec`. This is the only component allowed to know about the other
four; each of them stays independent and is injected here.

Precedence rules (explicit beats inferred, inferred beats default):

    style     request.style > persona.default_style > library default
    lens      request.lens  > shot.lens            > style.lens
    camera    request.camera > shot.camera_phrase  > style.camera_motion
    lighting  request.lighting                     > style.lighting
    motion    request.motion > shot.motion_phrase  > style.motion_phrase
    fps       request.fps                          > style.fps
    lora      request.lora                         > persona.lora_path

Every resolution is recorded in a trace, so a generated frame can always
answer "why did it look like this?".
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .contracts import (
    GENERATION_SPEC_FIELDS,
    GenerationKind,
    GenerationSpec,
    PersonaMemory,
    PromptBlocks,
    ShotPreset,
    StylePreset,
)
from .memory_resolver import MemoryResolver
from .prompt_compiler import PromptCompiler
from .shot_resolver import ShotResolver
from .style_resolver import DEFAULT_STYLE_ID, StyleResolver


@dataclass
class ResolutionTrace:
    """Where each decision came from. Attached to logs and job records."""

    persona_id: str | None = None
    persona_name: str | None = None
    persona_applied: bool = False
    style_id: str = ""
    style_source: str = "library-default"
    shot_code: str | None = None
    shot_applied: bool = False
    sources: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "persona_id": self.persona_id,
            "persona_name": self.persona_name,
            "persona_applied": self.persona_applied,
            "style_id": self.style_id,
            "style_source": self.style_source,
            "shot_code": self.shot_code,
            "shot_applied": self.shot_applied,
            "sources": dict(self.sources),
        }


@dataclass
class BuildResult:
    """A spec plus the trace that explains it."""

    spec: GenerationSpec
    trace: ResolutionTrace


class GenerationSpecBuilder:
    """Builds the single object providers receive."""

    def __init__(
        self,
        *,
        memory: MemoryResolver | None = None,
        styles: StyleResolver | None = None,
        shots: ShotResolver | None = None,
        compiler: PromptCompiler | None = None,
    ) -> None:
        # Collaborators are injected, never imported-and-hardwired by callers,
        # so a test can build a spec with stubs and no database.
        self.memory = memory or MemoryResolver()
        self.styles = styles or StyleResolver()
        self.shots = shots or ShotResolver()
        self.compiler = compiler or PromptCompiler()

    # ------------------------------------------------------------------- build

    def build(
        self,
        *,
        prompt: str,
        kind: GenerationKind | str = GenerationKind.IMAGE,
        project_id: str | None = None,
        user_id: str | None = None,
        persona_id: str | None = None,
        wardrobe: list[str] | None = None,
        style: str | None = None,
        shot: str | None = None,
        provider: str = "",
        aspect_ratio: str = "16:9",
        fps: int | None = None,
        duration: float = 5.0,
        seed: int | None = None,
        lora: str | None = None,
        controlnet: str = "none",
        camera: str | None = None,
        lens: str | None = None,
        lighting: str | None = None,
        motion: str | None = None,
        weather: str = "",
        environment: str | None = None,
        negative_prompt: str = "",
        resolution: int | str | None = None,
        guidance_scale: float | str | None = None,
        steps: int | str | None = None,
        ip_adapter_scale: float | str | None = None,
        mode: str | None = None,
        cinematic_mode: bool = True,
        slow_motion: bool = False,
        native_audio: bool = False,
    ) -> GenerationSpec:
        """Compile a full GenerationSpec. See `build_traced` for the rationale."""

        return self.build_traced(
            prompt=prompt,
            kind=kind,
            project_id=project_id,
            user_id=user_id,
            persona_id=persona_id,
            wardrobe=wardrobe,
            style=style,
            shot=shot,
            provider=provider,
            aspect_ratio=aspect_ratio,
            fps=fps,
            duration=duration,
            seed=seed,
            lora=lora,
            controlnet=controlnet,
            camera=camera,
            lens=lens,
            lighting=lighting,
            motion=motion,
            weather=weather,
            environment=environment,
            negative_prompt=negative_prompt,
            resolution=resolution,
            guidance_scale=guidance_scale,
            steps=steps,
            ip_adapter_scale=ip_adapter_scale,
            mode=mode,
            cinematic_mode=cinematic_mode,
            slow_motion=slow_motion,
            native_audio=native_audio,
        ).spec

    def build_traced(self, **kwargs: object) -> BuildResult:
        """Build a spec and return the trace of every resolution."""

        prompt = str(kwargs.get("prompt") or "")
        persona_id = _opt_str(kwargs.get("persona_id"))
        requested_style = _opt_str(kwargs.get("style"))
        requested_shot = _opt_str(kwargs.get("shot"))
        # PR004: the persona wardrobe block narrows to the project's selected
        # items when (and only when) the request carries a selection.
        wardrobe_selection = kwargs.get("wardrobe")
        if wardrobe_selection is not None:
            wardrobe_selection = [str(name) for name in wardrobe_selection if str(name).strip()]

        persona: PersonaMemory | None = self.memory.resolve(persona_id)
        persona_applied = persona is not None and bool(self.memory.identity_phrase(persona))

        style, style_source = self._resolve_style(requested_style, persona)
        shot_preset: ShotPreset | None = self.shots.resolve(requested_shot)

        trace = ResolutionTrace(
            persona_id=persona.persona_id if persona else None,
            persona_name=persona.name if persona else None,
            persona_applied=persona_applied,
            style_id=style.style_id,
            style_source=style_source,
            shot_code=shot_preset.code if shot_preset else None,
            shot_applied=shot_preset is not None,
        )

        camera = self._pick(
            "camera",
            trace,
            _opt_str(kwargs.get("camera")),
            self.shots.camera_phrase(shot_preset),
            style.camera_motion,
        )
        lens = self._pick(
            "lens",
            trace,
            _opt_str(kwargs.get("lens")),
            self.shots.lens_phrase(shot_preset),
            style.lens,
        )
        lighting = self._pick(
            "lighting",
            trace,
            _opt_str(kwargs.get("lighting")),
            "",
            style.lighting,
        )
        motion = self._pick(
            "motion",
            trace,
            _opt_str(kwargs.get("motion")),
            self.shots.motion_phrase(shot_preset),
            self.styles.motion_phrase(style),
        )

        resolved_fps = kwargs.get("fps")
        if resolved_fps is None:
            resolved_fps = style.fps
            trace.sources["fps"] = f"style:{style.style_id}"
        else:
            trace.sources["fps"] = "request"

        resolved_lora = _opt_str(kwargs.get("lora"))
        if resolved_lora:
            trace.sources["lora"] = "request"
        else:
            resolved_lora = self.memory.lora_path(persona)
            trace.sources["lora"] = f"persona:{persona.persona_id}" if resolved_lora else "none"

        compiled = self.compiler.compile(
            PromptBlocks(
                subject=self.compiler.normalize(prompt),
                persona=self.memory.identity_phrase(persona, wardrobe=wardrobe_selection) if persona_applied else "",
                environment=_opt_str(kwargs.get("environment")) or self.styles.environment_phrase(style),
                style=self.styles.style_phrase(style),
                camera=camera,
                lens=lens,
                light=lighting,
                color=self.styles.color_phrase(style),
                motion=motion,
                output=self.compiler.output_block,
                negative=str(kwargs.get("negative_prompt") or ""),
            ),
            provider=kwargs.get("provider") or "",
        )

        spec = GenerationSpec(
            prompt_original=prompt,
            prompt_compiled=compiled.prompt,
            project_id=_opt_str(kwargs.get("project_id")),
            user_id=_opt_str(kwargs.get("user_id")),
            persona_id=persona.persona_id if persona_applied else None,
            style_id=style.style_id,
            negative_prompt=compiled.negative_prompt,
            camera=camera,
            lens=lens,
            lighting=lighting,
            motion=motion,
            weather=str(kwargs.get("weather") or ""),
            aspect_ratio=str(kwargs.get("aspect_ratio") or "16:9"),
            fps=int(resolved_fps),
            duration=float(kwargs.get("duration") or 5.0),
            provider=str(kwargs.get("provider") or ""),
            seed=_opt_int(kwargs.get("seed")),
            lora=resolved_lora,
            controlnet=str(kwargs.get("controlnet") or "none"),
            # Sampling extras. A provider receives only the spec, so these have
            # to travel inside it rather than beside it.
            resolution=_opt_int(kwargs.get("resolution")) or 1024,
            guidance_scale=_opt_float(kwargs.get("guidance_scale"), 7.5),
            steps=_opt_int(kwargs.get("steps")) or 28,
            ip_adapter_scale=_opt_float(kwargs.get("ip_adapter_scale"), 0.7),
            mode=str(kwargs.get("mode") or "text-to-video"),
            cinematic_mode=bool(kwargs.get("cinematic_mode", True)),
            slow_motion=bool(kwargs.get("slow_motion", False)),
            native_audio=bool(kwargs.get("native_audio", False)),
            motion_strength=_opt_float(kwargs.get("motion_strength"), 1.0),
            kind=GenerationKind(kwargs.get("kind") or GenerationKind.IMAGE),
        )
        return BuildResult(spec=spec, trace=trace)

    # ------------------------------------------------------------------ helpers

    def _resolve_style(self, requested: str | None, persona: PersonaMemory | None) -> tuple[StylePreset, str]:
        if requested and self.styles.is_known(requested):
            return self.styles.resolve(requested), "request"
        if persona and persona.default_style and self.styles.is_known(persona.default_style):
            return self.styles.resolve(persona.default_style), f"persona:{persona.persona_id}"
        if requested:
            # Asked for something the library does not have: stay neutral
            # instead of quietly borrowing another style's look.
            return self.styles.resolve(requested), "unknown-fallback-neutral"
        return self.styles.resolve(DEFAULT_STYLE_ID), "library-default"

    @staticmethod
    def _pick(name: str, trace: ResolutionTrace, *candidates: str) -> str:
        """First non-empty candidate wins; the winner is recorded in the trace."""

        labels = ("request", "shot", "style")
        for label, candidate in zip(labels, candidates):
            if candidate and candidate.strip():
                trace.sources[name] = label
                return candidate.strip()
        trace.sources[name] = "none"
        return ""


def _opt_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _opt_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _opt_float(value: object, default: float) -> float:
    """Coerce a sampling parameter, falling back to the documented default.

    Accepts the string forms the API schemas use (resolution arrives as
    "2048", guidance as "7.5") so the Core never has to know which side
    stringified the value.
    """

    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


#: The mandatory field list, re-exported so API schemas can validate against the
#: same source of truth the Core uses.
MANDATORY_SPEC_FIELDS = GENERATION_SPEC_FIELDS
