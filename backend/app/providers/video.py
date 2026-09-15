"""Optional Wan / Hunyuan video provider boundary.

ETAPA 3: this provider receives **only** a `GenerationSpec`. The worker owns
orchestration; this adapter owns model-specific inference.

ETAPA 10: `HunyuanVideoProvider` joins `WanVideoProvider`. `GET /api/v1/models/video`
already advertised `hunyuan-video` as `planned-provider`; it now has an adapter,
so the registry routes to it instead of silently running Wan.

The two share everything that is genuinely the same — loading, LoRA, health,
encoding — through `_DiffusersVideoProvider`, and differ only where the models
actually differ: pipeline class, frame-count rule and default resolution.

Install the video GPU profile before enabling it on a CUDA worker.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..core.contracts import GenerationSpec
from .common import (
    apply_lora,
    cuda_availability,
    generator_for,
    health_report,
    require_cuda,
    supported_kwargs,
)


@dataclass
class VideoGenerationOutput:
    path: str
    duration_seconds: int
    fps: int


class VideoProvider(ABC):
    """Contract every video provider implements.

    As with `ImageProvider`, the signature is the enforcement point: a video
    provider cannot be handed a prompt string, because it does not accept one.
    """

    @abstractmethod
    def generate(self, spec: GenerationSpec, output_dir: str) -> VideoGenerationOutput:
        """Render `spec` and persist the resulting MP4 under `output_dir`."""

    @abstractmethod
    def health(self) -> dict[str, Any]:
        """Report whether this provider could run right now."""


#: Spec fields every diffusers video adapter consumes. Hoisted to module level
#: so a subclass can extend it rather than copy it — copying is how the first
#: draft of `HunyuanVideoProvider` ended up consuming `steps` without declaring
#: it.
VIDEO_CONSUMED_SPEC_FIELDS: frozenset[str] = frozenset(
    {
        "prompt_compiled",
        "negative_prompt",
        "aspect_ratio",
        "fps",
        "duration",
        "guidance_scale",
        "seed",
        "lora",
    }
)


class _DiffusersVideoProvider(VideoProvider):
    """What every diffusers-backed video adapter does identically.

    Subclasses declare three things and inherit the rest: the diffusers pipeline
    class name, the frame-count rule, and the default dimensions per aspect
    ratio. Everything else — CUDA checks, LoRA, kwarg filtering, encoding,
    health — has one implementation.
    """

    #: Spec fields the local pipeline cannot honour. Declared rather than
    #: silently dropped, so a caller can tell "not supported here" from "forgot".
    #: Camera and lens language still reaches the model, but through
    #: `prompt_compiled` rather than as pipeline arguments.
    UNSUPPORTED_SPEC_FIELDS: frozenset[str] = frozenset(
        {"cinematic_mode", "slow_motion", "native_audio", "controlnet", "reference_path", "mode"}
    )

    #: diffusers class to import, e.g. "WanPipeline".
    PIPELINE_CLASS: str = ""

    #: Default dimensions per aspect ratio, before `spec.resolution` overrides.
    DIMENSIONS: dict[str, tuple[int, int]] = {}

    def __init__(self, model_id: str) -> None:
        self.model_id = model_id
        self._pipeline = None

    # ------------------------------------------------------------------ runtime

    def _load(self):
        if self._pipeline is None:
            try:
                import torch
                from diffusers import __dict__ as diffusers_namespace
            except ImportError as error:
                raise RuntimeError("Video GPU dependencies are not installed") from error
            pipeline_class = diffusers_namespace.get(self.PIPELINE_CLASS)
            if pipeline_class is None:
                raise RuntimeError(
                    f"the installed diffusers has no {self.PIPELINE_CLASS}; upgrade diffusers"
                )
            require_cuda()
            self._pipeline = pipeline_class.from_pretrained(self.model_id, torch_dtype=torch.bfloat16)
            self._pipeline.to("cuda")
        return self._pipeline

    def _apply_lora(self, pipeline, lora: str | None) -> None:
        apply_lora(pipeline, lora)

    # ---------------------------------------------------------------- generate

    def generate(self, spec: GenerationSpec, output_dir: str) -> VideoGenerationOutput:
        pipeline = self._load()
        self._apply_lora(pipeline, spec.lora)

        width, height = self.dimensions(spec)
        arguments = self.arguments(spec, width, height)
        accepted = _supported_kwargs(pipeline, arguments)

        result = pipeline(**accepted).frames[0]
        # Named by spec_id: two concurrent renders must not overwrite one file.
        output = Path(output_dir) / f"{spec.spec_id}.mp4"
        output.parent.mkdir(parents=True, exist_ok=True)
        try:
            import imageio.v3 as iio

            iio.imwrite(output, result, fps=spec.fps, codec="libx264")
        except ImportError as error:
            raise RuntimeError("imageio and imageio-ffmpeg are required for video encoding") from error
        return VideoGenerationOutput(str(output), int(spec.duration), spec.fps)

    def health(self) -> dict[str, Any]:
        available, reason = cuda_availability()
        return health_report(
            self.model_id,
            reason=reason,
            available=available,
            loaded=self._pipeline is not None,
        )

    # -------------------------------------------------------------- per-model

    @classmethod
    def dimensions(cls, spec: GenerationSpec) -> tuple[int, int]:
        """Dimensions for the spec's aspect ratio."""

        return cls.DIMENSIONS.get(spec.aspect_ratio, cls.DIMENSIONS.get("16:9", (832, 480)))

    def arguments(self, spec: GenerationSpec, width: int, height: int) -> dict[str, Any]:
        """Map a GenerationSpec onto candidate pipeline kwargs.

        Pure and torch-free. `num_frames` is derived from the spec's own `fps`
        and `duration`, so a provider can no longer disagree with the spec about
        how long the clip is.
        """

        return {
            "prompt": spec.prompt_compiled,
            "negative_prompt": spec.negative_prompt,
            "num_frames": frame_count(spec),
            "width": width,
            "height": height,
            "guidance_scale": spec.guidance_scale,
            "generator": _generator(spec.seed),
        }


class WanVideoProvider(_DiffusersVideoProvider):
    """Wan 2.1 text-to-video."""

    #: Spec fields this provider consumes.
    CONSUMED_SPEC_FIELDS: frozenset[str] = VIDEO_CONSUMED_SPEC_FIELDS

    PIPELINE_CLASS = "WanPipeline"
    DIMENSIONS = {"16:9": (832, 480), "9:16": (480, 832), "1:1": (512, 512)}

    def __init__(self, model_id: str = "Wan-AI/Wan2.1-T2V-1.3B-Diffusers") -> None:
        super().__init__(model_id)


class HunyuanVideoProvider(_DiffusersVideoProvider):
    """Hunyuan video, via the diffusers-format community weights.

    The frame-count rule differs from Wan's. Wan requires 4n+1 frames; Hunyuan
    has no such constraint, so the count comes straight from `fps * duration`
    and is only floored at one frame. Snapping a Hunyuan render to 4n+1 would
    silently change its duration.
    """

    #: Hunyuan's text encoder is a Llama model, so `negative_prompt` is accepted
    #: by the pipeline signature but has far less effect than on Wan. Declared
    #: consumed rather than unsupported, because it is genuinely passed through.
    PIPELINE_CLASS = "HunyuanVideoPipeline"
    DIMENSIONS = {"16:9": (1280, 720), "9:16": (720, 1280), "1:1": (960, 960)}

    #: `steps` is declared here and not on Wan because only this adapter maps it
    #: onto `num_inference_steps`. Found by `test_the_declared_fields_match_the_code`:
    #: the first draft copied Wan's declaration and quietly consumed one field
    #: more than it admitted — the same defect ETAPA 10 was written to remove.
    CONSUMED_SPEC_FIELDS: frozenset[str] = VIDEO_CONSUMED_SPEC_FIELDS | frozenset({"steps"})

    def __init__(self, model_id: str = "hunyuanvideo-community/HunyuanVideo") -> None:
        super().__init__(model_id)

    def arguments(self, spec: GenerationSpec, width: int, height: int) -> dict[str, Any]:
        return {
            "prompt": spec.prompt_compiled,
            "negative_prompt": spec.negative_prompt,
            "num_frames": hunyuan_frame_count(spec),
            "width": width,
            "height": height,
            "guidance_scale": spec.guidance_scale,
            "num_inference_steps": spec.steps,
            "generator": _generator(spec.seed),
        }


def frame_count(spec: GenerationSpec) -> int:
    """Frames implied by the spec, snapped to Wan's 4n+1 requirement.

    Wan rejects a frame count that is not of the form 4n+1, so the value derived
    from `fps * duration` is snapped rather than passed through and rejected by
    the pipeline.
    """

    frames = max(1, round(spec.fps * spec.duration))
    return max(1, frames - (frames % 4) + 1)


def hunyuan_frame_count(spec: GenerationSpec) -> int:
    """Frames implied by the spec, unsnapped.

    Hunyuan has no 4n+1 constraint, so the count is exactly `fps * duration`.
    """

    return max(1, round(spec.fps * spec.duration))


#: Module-level mapping kept for the callers and tests that use it by name.
def pipeline_arguments(spec: GenerationSpec, width: int, height: int) -> dict[str, Any]:
    """Map a GenerationSpec onto candidate Wan pipeline kwargs."""

    return WanVideoProvider("x").arguments(spec, width, height)


#: Shared since ETAPA 10. Kept as module-level names because they are part of
#: this module's tested surface.
_supported_kwargs = supported_kwargs
_generator = generator_for


def _dimensions(aspect_ratio: str) -> tuple[int, int]:
    """Wan's default dimensions for an aspect ratio."""

    return WanVideoProvider.DIMENSIONS.get(aspect_ratio, (832, 480))
