"""Singleton Wan 2.2 text-to-video runtime.

Wan is loaded lazily and kept in memory for the life of the worker.  CUDA is a
hard requirement: unlike the legacy orchestration providers, this runtime never
silently substitutes a mock or a CPU implementation for a requested render.
"""
from __future__ import annotations

import inspect
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from ..system import gpu_runtime

WAN_MODEL_ID = "Wan2.2-T2V-A14B"
WAN_CHECKPOINT_ID = "Wan-AI/Wan2.2-T2V-A14B-Diffusers"
WAN_LABEL = WAN_MODEL_ID


@dataclass(frozen=True)
class WanArtifact:
    path: str
    width: int
    height: int
    duration: float
    fps: int
    model: str = WAN_LABEL


class WanRuntime:
    """One process-wide Wan pipeline with lazy CUDA initialisation."""

    _instance: "WanRuntime | None" = None
    _instance_lock = threading.Lock()

    def __new__(cls, *args: Any, **kwargs: Any) -> "WanRuntime":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        model_id: str = WAN_MODEL_ID,
        *,
        pipeline_loader: Callable[[str, Any], Any] | None = None,
    ) -> None:
        if getattr(self, "_configured", False):
            # A test/deployment may supply a loader before the first load; do
            # not replace an already resident pipeline or break singleton use.
            if pipeline_loader is not None and self._pipeline is None:
                self._pipeline_loader = pipeline_loader
            return
        self.model_id = model_id
        self._pipeline_loader = pipeline_loader
        self._pipeline: Any | None = None
        self._load_lock = threading.RLock()
        self._configured = True
        self._compiled = False

    @classmethod
    def instance(cls) -> "WanRuntime":
        return cls()

    @property
    def loaded(self) -> bool:
        return self._pipeline is not None

    @property
    def pipeline(self) -> Any | None:
        return self._pipeline

    def reset(self) -> None:
        with self._load_lock:
            self._pipeline = None
            self._compiled = False

    @staticmethod
    def _require_cuda(torch: Any) -> None:
        if not getattr(getattr(torch, "cuda", None), "is_available", lambda: False)():
            raise RuntimeError("CUDA GPU is required")

    def _load_default(self, torch: Any) -> Any:
        try:
            from diffusers import WanPipeline
        except ImportError as error:  # pragma: no cover - deployment dependent
            raise RuntimeError("Diffusers GPU dependencies are not installed") from error
        dtype = getattr(torch, "float16", None)
        if dtype is None:
            raise RuntimeError("Torch float16 support is unavailable")
        pipeline = WanPipeline.from_pretrained(WAN_CHECKPOINT_ID, torch_dtype=dtype)
        if callable(getattr(pipeline, "enable_model_cpu_offload", None)):
            pipeline.enable_model_cpu_offload()
        elif callable(getattr(pipeline, "to", None)):
            pipeline.to("cuda")
        return pipeline

    @staticmethod
    def _try_compile(torch: Any, pipeline: Any) -> bool:
        compiler = getattr(torch, "compile", None)
        target = getattr(pipeline, "transformer", None) or getattr(pipeline, "unet", None)
        if not callable(compiler) or target is None:
            return False
        try:
            compiled = compiler(target)
            if hasattr(pipeline, "transformer"):
                pipeline.transformer = compiled
            else:
                pipeline.unet = compiled
            return True
        except Exception:  # noqa: BLE001 - optional optimisation
            return False

    # Naming aliases keep the runtime easy to use from worker integrations.
    def load_model(self) -> Any:
        return self.load()

    def get_pipeline(self) -> Any:
        return self.load()

    def load(self) -> Any:
        if self._pipeline is not None:
            return self._pipeline
        with self._load_lock:
            if self._pipeline is not None:
                return self._pipeline
            try:
                import torch
            except ImportError as error:  # pragma: no cover
                raise RuntimeError("Video GPU dependencies are not installed") from error
            self._require_cuda(torch)
            dtype = getattr(torch, "float16", None)
            if dtype is None:
                raise RuntimeError("Torch float16 support is unavailable")
            if self._pipeline_loader is not None:
                pipeline = self._pipeline_loader(self.model_id, dtype)
            else:
                pipeline = self._load_default(torch)
            self._compiled = self._try_compile(torch, pipeline)
            self._pipeline = pipeline
            return pipeline

    @staticmethod
    def _accepted(pipeline: Any, values: dict[str, Any]) -> dict[str, Any]:
        try:
            signature = inspect.signature(pipeline.__call__)
        except (TypeError, ValueError):
            return values
        if any(parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values()):
            return values
        accepted = set(signature.parameters)
        return {key: value for key, value in values.items() if key in accepted}

    @staticmethod
    def _generator(torch: Any, seed: int | None) -> Any:
        if seed is None:
            return None
        return torch.Generator(device="cuda").manual_seed(seed)

    @staticmethod
    def _dimensions(aspect: str) -> tuple[int, int]:
        dimensions = {
            "16:9": (1280, 720),
            "9:16": (720, 1280),
            "1:1": (960, 960),
            "4:3": (1152, 864),
            "3:4": (864, 1152),
        }
        return dimensions.get(aspect, dimensions["16:9"])

    @staticmethod
    def _frames(result: Any) -> Any:
        frames = getattr(result, "frames", None)
        if frames is None:
            raise RuntimeError("Wan returned no video frames")
        # Diffusers returns [frames] for a batch of one. A raw frame sequence
        # is also accepted for small custom pipelines and test doubles.
        if isinstance(frames, (list, tuple)) and len(frames) == 1:
            first = frames[0]
            if isinstance(first, (list, tuple)):
                return first
            if hasattr(first, "shape") and len(getattr(first, "shape", ())) >= 4:
                return first
        return frames

    @staticmethod
    def _encode(frames: Any, destination: Path, fps: int) -> None:
        try:
            import imageio.v3 as iio
        except ImportError as error:  # pragma: no cover - deployment dependency
            raise RuntimeError("imageio and imageio-ffmpeg are required for video encoding") from error
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            iio.imwrite(destination, frames, fps=fps, codec="libx264")
        except TypeError:
            # Older imageio plugins do not accept codec; their ffmpeg writer
            # still produces a standards-compliant MP4 with the same fps.
            iio.imwrite(destination, frames, fps=fps)

    def generate(
        self,
        prompt: str,
        *,
        duration: float = 5,
        fps: int = 24,
        aspect: str = "16:9",
        seed: int | None = None,
        output_dir: str | Path = "media/runtime/videos",
    ) -> WanArtifact:
        """Generate frames and encode one MP4, reusing the loaded pipeline."""

        if not prompt.strip():
            raise ValueError("prompt is required")
        if duration <= 0:
            raise ValueError("duration must be positive")
        if fps <= 0:
            raise ValueError("fps must be positive")
        pipeline = self.load()
        import torch

        width, height = self._dimensions(aspect)
        frame_count = max(1, round(duration * fps))
        values = {
            "prompt": prompt,
            "num_frames": frame_count,
            "width": width,
            "height": height,
            "generator": self._generator(torch, seed),
        }
        accepted = self._accepted(pipeline, values)
        result = pipeline(**accepted)
        frames = self._frames(result)
        output = Path(output_dir) / f"{uuid4().hex}.mp4"
        self._encode(frames, output, fps)
        return WanArtifact(str(output), width, height, float(duration), fps)

    generate_video = generate

    def status(self) -> dict[str, Any]:
        gpu = gpu_runtime.detect_gpu()
        return {
            "model": WAN_LABEL,
            "loaded": self.loaded,
            "gpu": bool(gpu.get("available")),
        }


wan_runtime = WanRuntime()


def get_wan_runtime() -> WanRuntime:
    return wan_runtime


__all__ = ["WAN_CHECKPOINT_ID", "WAN_MODEL_ID", "WanArtifact", "WanRuntime", "wan_runtime", "get_wan_runtime"]
