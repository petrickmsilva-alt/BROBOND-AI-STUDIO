"""PR009 — Wan real connector (ETAPA 2).

Universal video connector for Wan 2.1 (and, sharing the same base, Hunyuan).
The PR007 rule survives: Wan and Hunyuan share everything that is genuinely
the same — loading, LoRA, kwarg filtering, encoding, health — and differ only
where the models differ: pipeline classes, the frame-count rule and default
dimensions. `WanProvider.__dict__` carries no `generate_video` of its own.

Contract, unchanged from ETAPA 3 and enforced by signature: the connector
receives **only** a `GenerationSpec`; the only text that reaches the pipeline
is `spec.prompt_compiled`.

Supported operations and controls:

* `text-to-video`  — `WanPipeline`
* `image-to-video` — `WanImageToVideoPipeline`, driven by `spec.reference_path`
* `duration` / `fps` — the frame count is derived from the spec's own timing
  (snapped to Wan's 4n+1 requirement) and the clip is encoded at `spec.fps`
* `motion_strength` — carried by the spec and passed through; pipelines that
  have no such control filter it out at call time
* `seed` — seeded CUDA generator (`None` means "let the model choose")
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ..core.contracts import GenerationKind, GenerationSpec
from .base_provider import (
    BaseProvider,
    ProviderAsset,
    ProviderCapabilities,
    ProviderEstimate,
    ProviderHealth,
    STATUS_READY,
    STATUS_UNAVAILABLE,
    health_timestamp,
    unsupported,
)
from .common import (
    apply_lora,
    cuda_availability,
    generator_for,
    load_reference_image,
    require_cuda,
    supported_kwargs,
)

WAN_PROVIDER_ID = "wan-2.1-t2v"
WAN_LABEL = "Wan"
WAN_MODEL_ID = "Wan-AI/Wan2.1-T2V-1.3B-Diffusers"
WAN_VERSION = "wan-real-connector-v1"
WAN_MAX_RESOLUTION = "832x832"
WAN_PROMPT_BUDGET = 1200
WAN_ESTIMATED_SECONDS_PER_SECOND = 12.0
#: Documented default deadline; `core.config` (ENV-overridable) is the source
#: of truth the TimeoutManager reads.
WAN_TIMEOUT_SECONDS = 300.0

HUNYUAN_PROVIDER_ID = "hunyuan-video"
HUNYUAN_LABEL = "Hunyuan"
HUNYUAN_MODEL_ID = "hunyuanvideo-community/HunyuanVideo"
HUNYUAN_VERSION = "hunyuan-real-connector-v1"
HUNYUAN_MAX_RESOLUTION = "1280x1280"

MODE_TEXT_TO_VIDEO = "text-to-video"
MODE_IMAGE_TO_VIDEO = "image-to-video"
WAN_MODES: tuple[str, ...] = (MODE_TEXT_TO_VIDEO, MODE_IMAGE_TO_VIDEO)


@dataclass(frozen=True)
class WanRequest:
    """Everything the Wan connector receives for one render — spec only."""

    mode: str
    prompt: str
    negative_prompt: str
    seed: int | None
    lora: str | None
    aspect_ratio: str
    width: int
    height: int
    duration: float
    fps: int
    motion_strength: float
    guidance_scale: float
    steps: int
    reference_path: str | None
    spec_id: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def resolve_wan_mode(spec: GenerationSpec) -> str:
    """The video mode for a spec; only an explicit value selects img2vid."""

    if spec.mode == MODE_IMAGE_TO_VIDEO:
        return MODE_IMAGE_TO_VIDEO
    return MODE_TEXT_TO_VIDEO


def wan_frame_count(spec: GenerationSpec) -> int:
    """Frames implied by the spec, snapped to Wan's 4n+1 requirement.

    Wan rejects a frame count that is not of the form 4n+1, so the value
    derived from `fps * duration` is snapped rather than refused by the
    pipeline at inference time.
    """

    frames = max(1, round(spec.fps * spec.duration))
    return max(1, frames - (frames % 4) + 1)


def hunyuan_frame_count(spec: GenerationSpec) -> int:
    """Frames implied by the spec, unsnapped — Hunyuan has no 4n+1 rule."""

    return max(1, round(spec.fps * spec.duration))


def wan_pipeline_arguments(request: WanRequest, *, frame_count: int) -> dict[str, Any]:
    """Map a WanRequest onto candidate pipeline kwargs (pure, torch-free)."""

    arguments: dict[str, Any] = {
        "prompt": request.prompt,
        "negative_prompt": request.negative_prompt,
        "num_frames": frame_count,
        "width": request.width,
        "height": request.height,
        "guidance_scale": request.guidance_scale,
        "motion_strength": request.motion_strength,
        "generator": generator_for(request.seed),
    }
    if request.mode == MODE_IMAGE_TO_VIDEO:
        arguments["image"] = load_reference_image(request.reference_path)
    return arguments


class VideoPipelineLoader:
    """Lazy diffusers loader for video pipelines; CPU-safe at import time."""

    def __call__(self, model_id: str, pipeline_class_name: str):
        try:
            import torch
            from diffusers import __dict__ as diffusers_namespace
        except ImportError as error:
            raise RuntimeError("Video GPU dependencies are not installed") from error
        pipeline_class = diffusers_namespace.get(pipeline_class_name)
        if pipeline_class is None:
            raise RuntimeError(
                f"the installed diffusers has no {pipeline_class_name}; upgrade diffusers"
            )
        require_cuda()
        pipeline = pipeline_class.from_pretrained(model_id, torch_dtype=torch.bfloat16)
        pipeline.to("cuda")
        return pipeline


class _DiffusersVideoRealConnector(BaseProvider):
    """What every diffusers-backed video connector does identically.

    Subclasses declare the pipeline class per mode, the frame-count rule and
    the default dimensions, and inherit everything else.
    """

    provider_id = ""
    label = ""
    version = ""
    model_id_default = ""
    max_resolution = WAN_MAX_RESOLUTION

    #: diffusers pipeline class per mode. A mode absent from the table is
    #: refused with `unsupported` — never silently remapped onto another mode.
    PIPELINE_CLASS_BY_MODE: dict[str, str] = {}

    #: Default dimensions per aspect ratio.
    DIMENSIONS: dict[str, tuple[int, int]] = {}

    #: Spec fields the connector consumes / cannot honour. Declared, matching
    #: the ETAPA 10 rule: what a provider does not honour is visible.
    CONSUMED_SPEC_FIELDS: frozenset[str] = frozenset(
        {
            "prompt_compiled",
            "negative_prompt",
            "aspect_ratio",
            "fps",
            "duration",
            "guidance_scale",
            "seed",
            "lora",
            "mode",
            "motion_strength",
            "reference_path",
        }
    )
    UNSUPPORTED_SPEC_FIELDS: frozenset[str] = frozenset(
        {
            "cinematic_mode",
            "slow_motion",
            "native_audio",
            "controlnet",
            "ip_adapter_scale",
            "resolution",
            "steps",
        }
    )

    def __init__(
        self,
        model_id: str | None = None,
        *,
        pipeline_loader: Callable[[str, str], Any] | None = None,
    ) -> None:
        self.model_id = model_id or self.model_id_default
        self._pipelines: dict[str, Any] = {}
        self._pipeline_loader = pipeline_loader or VideoPipelineLoader()

    # ------------------------------------------------------------- interface

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            max_resolution=self.max_resolution,
            supports_video=True,
            supports_image=False,
            supports_lora=True,
            supports_upscale=False,
            supports_seed=True,
            supports_negative_prompt=True,
            prompt_budget=WAN_PROMPT_BUDGET,
        )

    def generate_image(self, spec: GenerationSpec, output_dir: str | Path) -> ProviderAsset:
        raise unsupported(self.provider_id, "image generation")

    def upscale(self, spec: GenerationSpec, asset_path: str | Path, output_dir: str | Path) -> ProviderAsset:
        raise unsupported(self.provider_id, "upscale")

    def generate_video(self, spec: GenerationSpec, output_dir: str | Path) -> ProviderAsset:
        request = self.request_from_spec(spec)
        pipeline_class_name = self.PIPELINE_CLASS_BY_MODE.get(request.mode)
        if pipeline_class_name is None:
            raise unsupported(self.provider_id, request.mode)
        if request.mode == MODE_IMAGE_TO_VIDEO and not request.reference_path:
            raise ValueError(f"{self.provider_id} image-to-video requires spec.reference_path")

        pipeline = self._pipeline_for(request.mode, pipeline_class_name)
        apply_lora(pipeline, request.lora)
        frame_count = self.frame_count(spec)
        accepted = supported_kwargs(
            pipeline, self.pipeline_arguments(request, frame_count=frame_count)
        )
        result = pipeline(**accepted)
        frames = result.frames[0]

        output = Path(output_dir) / f"{request.spec_id}.mp4"
        output.parent.mkdir(parents=True, exist_ok=True)
        try:
            import imageio.v3 as iio
        except ImportError as error:
            raise RuntimeError("imageio and imageio-ffmpeg are required for video encoding") from error
        iio.imwrite(output, frames, fps=request.fps, codec="libx264")
        return ProviderAsset(
            path=str(output),
            kind=GenerationKind.VIDEO.value,
            provider_id=self.provider_id,
            duration_seconds=float(request.duration),
            fps=request.fps,
            metadata={
                "mode": request.mode,
                "model_id": self.model_id,
                "seed": request.seed,
                "num_frames": frame_count,
                "motion_strength": request.motion_strength,
            },
        )

    def health(self) -> ProviderHealth:
        available, reason = cuda_availability()
        return ProviderHealth(
            id=self.provider_id,
            label=self.label,
            status=STATUS_READY if available else STATUS_UNAVAILABLE,
            latency_ms=0.0,
            version=self.version,
            capabilities=self.capabilities(),
            reason=reason,
            loaded=bool(self._pipelines),
            last_health_at=health_timestamp(),
        )

    def estimate(self, spec: GenerationSpec) -> ProviderEstimate:
        return ProviderEstimate(
            provider_id=self.provider_id,
            kind=GenerationKind.VIDEO.value,
            estimated_seconds=max(1.0, float(spec.duration) * WAN_ESTIMATED_SECONDS_PER_SECOND),
            notes="wan real connector estimate",
        )

    # ------------------------------------------------------------- per-model

    def request_from_spec(self, spec: GenerationSpec) -> WanRequest:
        """Pure spec -> request mapping; unit-testable without torch."""

        mode = resolve_wan_mode(spec)
        width, height = self.dimensions_for(spec.aspect_ratio)
        return WanRequest(
            mode=mode,
            prompt=spec.prompt_compiled,
            negative_prompt=spec.negative_prompt,
            seed=spec.seed,
            lora=spec.lora,
            aspect_ratio=spec.aspect_ratio,
            width=width,
            height=height,
            duration=float(spec.duration),
            fps=spec.fps,
            motion_strength=spec.motion_strength,
            guidance_scale=spec.guidance_scale,
            steps=spec.steps,
            reference_path=spec.reference_path if mode == MODE_IMAGE_TO_VIDEO else None,
            spec_id=spec.spec_id,
        )

    @classmethod
    def dimensions_for(cls, aspect_ratio: str) -> tuple[int, int]:
        return cls.DIMENSIONS.get(aspect_ratio, cls.DIMENSIONS.get("16:9", (832, 480)))

    def frame_count(self, spec: GenerationSpec) -> int:
        return wan_frame_count(spec)

    def pipeline_arguments(self, request: WanRequest, *, frame_count: int) -> dict[str, Any]:
        return wan_pipeline_arguments(request, frame_count=frame_count)

    def _pipeline_for(self, mode: str, pipeline_class_name: str):
        if mode not in self._pipelines:
            self._pipelines[mode] = self._pipeline_loader(self.model_id, pipeline_class_name)
        return self._pipelines[mode]


class WanProvider(_DiffusersVideoRealConnector):
    """Wan 2.1 real connector: text-to-video and image-to-video."""

    provider_id = WAN_PROVIDER_ID
    label = WAN_LABEL
    version = WAN_VERSION
    model_id_default = WAN_MODEL_ID
    max_resolution = WAN_MAX_RESOLUTION

    PIPELINE_CLASS_BY_MODE = {
        MODE_TEXT_TO_VIDEO: "WanPipeline",
        MODE_IMAGE_TO_VIDEO: "WanImageToVideoPipeline",
    }
    DIMENSIONS = {"16:9": (832, 480), "9:16": (480, 832), "1:1": (512, 512)}


class HunyuanProvider(_DiffusersVideoRealConnector):
    """Hunyuan real connector (text-to-video only).

    The frame-count rule differs from Wan's: Hunyuan has no 4n+1 constraint, so
    the count comes straight from `fps * duration`. `steps` is consumed here
    (mapped onto `num_inference_steps`) and not on Wan — declared per class,
    never copied.
    """

    provider_id = HUNYUAN_PROVIDER_ID
    label = HUNYUAN_LABEL
    version = HUNYUAN_VERSION
    model_id_default = HUNYUAN_MODEL_ID
    max_resolution = HUNYUAN_MAX_RESOLUTION

    PIPELINE_CLASS_BY_MODE = {MODE_TEXT_TO_VIDEO: "HunyuanVideoPipeline"}
    DIMENSIONS = {"16:9": (1280, 720), "9:16": (720, 1280), "1:1": (960, 960)}

    CONSUMED_SPEC_FIELDS = _DiffusersVideoRealConnector.CONSUMED_SPEC_FIELDS | frozenset({"steps"})
    UNSUPPORTED_SPEC_FIELDS = _DiffusersVideoRealConnector.UNSUPPORTED_SPEC_FIELDS - frozenset({"steps"})

    def frame_count(self, spec: GenerationSpec) -> int:
        return hunyuan_frame_count(spec)

    def pipeline_arguments(self, request: WanRequest, *, frame_count: int) -> dict[str, Any]:
        arguments = wan_pipeline_arguments(request, frame_count=frame_count)
        arguments["num_inference_steps"] = request.steps
        return arguments
