"""PR011 — RunPod Wan connector (ETAPA 3).

Video generation on an external GPU cluster. The local diffusers connector in
`wan_provider.py` is untouched and still registered; this is a second
implementation of the same interface.

Operations
----------

| Operation      | `spec.mode`      | Needs a reference |
| -------------- | ---------------- | ----------------- |
| text-to-video  | `text-to-video`  | no                |
| image-to-video | `image-to-video` | yes               |

Controls honoured: `duration`, `fps`, `seed` and camera motion.

Camera motion without importing the Storyboard
----------------------------------------------
The Storyboard Engine plans the shot; the Director translates it; the Prompt
Compiler bakes it into `prompt_compiled`. By the time a spec reaches this
module, camera intent is already two typed fields — `spec.motion` (the named
move) and `spec.motion_strength` (its magnitude). This connector reads those
fields and maps them onto the worker's motion vocabulary. It does not import
`app.core.storyboard_engine`, `app.core.director` or anything downstream of
them, and `backend/tests/test_architecture_boundaries.py` enforces that at
build time.

`CAMERA_MOTIONS` is not a second source of truth for cinematography: it is a
translation table from the vocabulary the spec already carries into the string
this particular worker expects, the same way `PIPELINE_CLASS_BY_MODE` maps a
mode onto a diffusers class.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ..core.contracts import GenerationKind, GenerationSpec
from .base_provider import (
    ProviderAsset,
    ProviderCapabilities,
    ProviderEstimate,
    unsupported,
)
from .gpu_client import GpuClient
from .runpod_base import RunPodProvider

RUNPOD_WAN_PROVIDER_ID = "runpod-wan"
RUNPOD_WAN_LABEL = "RunPod Wan"
RUNPOD_WAN_MODEL_ID = "wan-2.1-t2v-14b"
RUNPOD_WAN_VERSION = "runpod-wan-connector-v1"
RUNPOD_WAN_MAX_RESOLUTION = "1280"
RUNPOD_WAN_PROMPT_BUDGET = 800
RUNPOD_WAN_VRAM = "48GB"
#: Cluster wall-clock per second of footage, queue included.
RUNPOD_WAN_SECONDS_PER_SECOND = 20.0

MODE_TEXT_TO_VIDEO = "text-to-video"
MODE_IMAGE_TO_VIDEO = "image-to-video"

SUPPORTED_MODES: frozenset[str] = frozenset({MODE_TEXT_TO_VIDEO, MODE_IMAGE_TO_VIDEO})

#: Duration and fps bounds the endpoint accepts. A spec outside them is
#: clamped, not rejected: a 30s request is a plan the cluster cannot execute,
#: and failing the whole batch over it would be worse than rendering the
#: longest clip it can — the clamp is recorded in the asset metadata.
MIN_DURATION_SECONDS = 1.0
MAX_DURATION_SECONDS = 10.0
MIN_FPS = 8
MAX_FPS = 30

#: Default dimensions per aspect ratio, matching the endpoint's presets.
DIMENSIONS: dict[str, tuple[int, int]] = {
    "16:9": (1280, 720),
    "9:16": (720, 1280),
    "1:1": (960, 960),
    "4:3": (1024, 768),
    "3:4": (768, 1024),
}

#: `spec.motion` (Director vocabulary) -> the worker's camera-motion token.
#: An unmapped value passes through unchanged rather than being dropped, so a
#: new Director move reaches the cluster before this table learns about it.
CAMERA_MOTIONS: dict[str, str] = {
    "": "static",
    "static": "static",
    "slow push in": "push_in",
    "push in": "push_in",
    "dolly in": "push_in",
    "pull back": "pull_out",
    "dolly out": "pull_out",
    "pan left": "pan_left",
    "pan right": "pan_right",
    "tilt up": "tilt_up",
    "tilt down": "tilt_down",
    "orbit": "orbit",
    "crane up": "crane_up",
    "handheld": "handheld",
    "tracking": "tracking",
}

WAN_CONSUMED_SPEC_FIELDS: frozenset[str] = frozenset(
    {
        "prompt_compiled",
        "negative_prompt",
        "aspect_ratio",
        "duration",
        "fps",
        "seed",
        "lora",
        "mode",
        "motion",
        "motion_strength",
        "guidance_scale",
        "steps",
        "reference_path",
    }
)
WAN_UNSUPPORTED_SPEC_FIELDS: frozenset[str] = frozenset(
    {"resolution", "controlnet", "ip_adapter_scale", "native_audio", "cinematic_mode", "slow_motion"}
)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def resolve_camera_motion(spec: GenerationSpec) -> str:
    """The worker's camera-motion token for this spec.

    Reads `spec.motion` only. The Storyboard is never consulted.
    """

    key = (spec.motion or "").strip().lower()
    return CAMERA_MOTIONS.get(key, key or "static")


def resolve_wan_mode(spec: GenerationSpec) -> str:
    return spec.mode if spec.mode in SUPPORTED_MODES else MODE_TEXT_TO_VIDEO


def dimensions_for_ratio(aspect_ratio: str) -> tuple[int, int]:
    return DIMENSIONS.get(aspect_ratio, DIMENSIONS["16:9"])


@dataclass(frozen=True)
class RunPodWanRequest:
    """One cluster video job, built only from the spec."""

    mode: str
    prompt: str
    negative_prompt: str
    width: int
    height: int
    duration: float
    fps: int
    frames: int
    seed: int | None
    lora: str | None
    aspect_ratio: str
    camera_motion: str
    motion_strength: float
    guidance_scale: float
    steps: int
    reference_path: str | None
    spec_id: str
    clamped: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def wan_request_from_spec(spec: GenerationSpec) -> RunPodWanRequest:
    """Pure spec -> request mapping; no I/O, no torch, no Storyboard."""

    mode = resolve_wan_mode(spec)
    width, height = dimensions_for_ratio(spec.aspect_ratio)
    duration = clamp(float(spec.duration), MIN_DURATION_SECONDS, MAX_DURATION_SECONDS)
    fps = int(clamp(float(spec.fps), MIN_FPS, MAX_FPS))
    return RunPodWanRequest(
        mode=mode,
        prompt=spec.prompt_compiled,
        negative_prompt=spec.negative_prompt,
        width=width,
        height=height,
        duration=duration,
        fps=fps,
        frames=max(1, round(duration * fps)),
        seed=spec.seed,
        lora=spec.lora,
        aspect_ratio=spec.aspect_ratio,
        camera_motion=resolve_camera_motion(spec),
        motion_strength=spec.motion_strength,
        guidance_scale=spec.guidance_scale,
        steps=spec.steps,
        reference_path=spec.reference_path if mode == MODE_IMAGE_TO_VIDEO else None,
        spec_id=spec.spec_id,
        clamped=duration != float(spec.duration) or fps != int(spec.fps),
    )


class RunPodWanProvider(RunPodProvider):
    """Wan video on a RunPod serverless endpoint."""

    provider_id = RUNPOD_WAN_PROVIDER_ID
    label = RUNPOD_WAN_LABEL
    version = RUNPOD_WAN_VERSION
    model_id_default = RUNPOD_WAN_MODEL_ID
    vram = RUNPOD_WAN_VRAM
    output_suffix = ".mp4"

    SUPPORTED_MODES = SUPPORTED_MODES
    CAMERA_MOTIONS = CAMERA_MOTIONS
    CONSUMED_SPEC_FIELDS = WAN_CONSUMED_SPEC_FIELDS
    UNSUPPORTED_SPEC_FIELDS = WAN_UNSUPPORTED_SPEC_FIELDS

    def __init__(self, model_id: str | None = None, *, client: GpuClient | None = None) -> None:
        super().__init__(model_id, client=client)

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            max_resolution=RUNPOD_WAN_MAX_RESOLUTION,
            supports_video=True,
            supports_image=False,
            supports_lora=True,
            supports_upscale=False,
            supports_seed=True,
            supports_negative_prompt=True,
            prompt_budget=RUNPOD_WAN_PROMPT_BUDGET,
        )

    @classmethod
    def supports_mode(cls, mode: str) -> bool:
        return mode in cls.SUPPORTED_MODES

    def payload_for(self, request: RunPodWanRequest, *, reference: str | None = None) -> dict[str, Any]:
        """The job envelope. The one place that knows the worker's field names."""

        payload: dict[str, Any] = {
            "operation": "video",
            "mode": request.mode,
            "model": self.model_id,
            "prompt": request.prompt,
            "negative_prompt": request.negative_prompt,
            "width": request.width,
            "height": request.height,
            "duration": request.duration,
            "fps": request.fps,
            "num_frames": request.frames,
            "camera_motion": request.camera_motion,
            "motion_strength": request.motion_strength,
            "guidance_scale": request.guidance_scale,
            "num_inference_steps": request.steps,
        }
        if request.seed is not None:
            payload["seed"] = request.seed
        if request.lora:
            payload["lora"] = request.lora
        if reference:
            payload["image"] = reference
        return payload

    def generate_video(self, spec: GenerationSpec, output_dir: str | Path) -> ProviderAsset:
        request = wan_request_from_spec(spec)
        reference: str | None = None
        if request.mode == MODE_IMAGE_TO_VIDEO:
            if not request.reference_path:
                raise ValueError("runpod wan image-to-video requires spec.reference_path")
            reference = self.upload_reference(request.reference_path)

        result = self.execute_job(self.payload_for(request, reference=reference))
        path = self.materialise(result, output_dir, request.spec_id)
        return self.asset(
            path,
            GenerationKind.VIDEO.value,
            self.asset_metadata(
                spec,
                result,
                mode=request.mode,
                camera_motion=request.camera_motion,
                motion_strength=request.motion_strength,
                num_frames=request.frames,
                clamped=request.clamped,
                vram=self.vram,
            ),
            duration_seconds=request.duration,
            fps=request.fps,
        )

    def generate_image(self, spec: GenerationSpec, output_dir: str | Path) -> ProviderAsset:
        raise unsupported(self.provider_id, "image generation")

    def upscale(self, spec: GenerationSpec, asset_path: str | Path, output_dir: str | Path) -> ProviderAsset:
        raise unsupported(self.provider_id, "upscale")

    def estimate(self, spec: GenerationSpec) -> ProviderEstimate:
        duration = clamp(float(spec.duration), MIN_DURATION_SECONDS, MAX_DURATION_SECONDS)
        return ProviderEstimate(
            provider_id=self.provider_id,
            kind=GenerationKind.VIDEO.value,
            estimated_seconds=max(1.0, duration * RUNPOD_WAN_SECONDS_PER_SECOND),
            notes="runpod wan cluster estimate",
        )
