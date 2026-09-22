"""Singleton FLUX.1-dev runtime.

This is the model-facing layer for PR010.  It deliberately does not import
Torch or Diffusers at module import time, which lets the API boot and report an
honest ``loaded: false`` status on machines without a GPU.  The first real
request loads the pipeline once; subsequent requests reuse the same object.
"""
from __future__ import annotations

import inspect
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from ..system import gpu_runtime

FLUX_MODEL_ID = "black-forest-labs/FLUX.1-dev"
FLUX_LABEL = "FLUX.1-dev"


@dataclass(frozen=True)
class FluxArtifact:
    path: str
    width: int
    height: int
    model: str = FLUX_LABEL


class FluxRuntime:
    """One process-wide FLUX pipeline with lazy CUDA initialisation."""

    _instance: "FluxRuntime | None" = None
    _instance_lock = threading.Lock()

    def __new__(cls, *args: Any, **kwargs: Any) -> "FluxRuntime":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        model_id: str = FLUX_MODEL_ID,
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
    def instance(cls) -> "FluxRuntime":
        return cls()

    @property
    def loaded(self) -> bool:
        return self._pipeline is not None

    @property
    def pipeline(self) -> Any | None:
        return self._pipeline

    def reset(self) -> None:
        """Release the reference; intended for a worker restart/test fixture."""

        with self._load_lock:
            self._pipeline = None
            self._compiled = False

    @staticmethod
    def _require_cuda(torch: Any) -> None:
        if not getattr(getattr(torch, "cuda", None), "is_available", lambda: False)():
            raise RuntimeError("CUDA GPU is required")

    def _load_default(self, torch: Any) -> Any:
        try:
            from diffusers import FluxPipeline
        except ImportError as error:  # pragma: no cover - depends on deployment
            raise RuntimeError("Diffusers GPU dependencies are not installed") from error
        dtype = getattr(torch, "float16", None)
        if dtype is None:  # a clear error for incomplete test doubles/deploys
            raise RuntimeError("Torch float16 support is unavailable")
        pipeline = FluxPipeline.from_pretrained(self.model_id, torch_dtype=dtype)
        # FLUX.1-dev is large enough that offload is safer than unconditionally
        # copying every component into VRAM.  A pipeline without offload uses a
        # normal CUDA placement as a fallback.
        if callable(getattr(pipeline, "enable_model_cpu_offload", None)):
            pipeline.enable_model_cpu_offload()
        elif callable(getattr(pipeline, "to", None)):
            pipeline.to("cuda")
        return pipeline

    @staticmethod
    def _try_compile(torch: Any, pipeline: Any) -> bool:
        """Compile the denoiser when this Torch build supports it.

        Compilation is best-effort because some Diffusers versions expose a
        transformer object that is not compilable.  It must never make a valid
        CUDA runtime unavailable.
        """

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
        """Load the pipeline once, under a lock, and return the cached object."""

        if self._pipeline is not None:
            return self._pipeline
        with self._load_lock:
            if self._pipeline is not None:
                return self._pipeline
            try:
                import torch
            except ImportError as error:  # pragma: no cover - deployment issue
                raise RuntimeError("Diffusers GPU dependencies are not installed") from error
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
        generator = torch.Generator(device="cuda")
        return generator.manual_seed(seed)

    def generate(
        self,
        prompt: str,
        *,
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 1024,
        steps: int = 28,
        seed: int | None = None,
        output_dir: str | Path = "media/runtime/images",
    ) -> FluxArtifact:
        """Generate and persist one PNG without reloading FLUX."""

        if not prompt.strip():
            raise ValueError("prompt is required")
        if width < 64 or height < 64:
            raise ValueError("width and height must be at least 64 pixels")
        if steps < 1:
            raise ValueError("steps must be positive")
        pipeline = self.load()
        import torch

        arguments = self._accepted(
            pipeline,
            {
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "width": width,
                "height": height,
                "num_inference_steps": steps,
                "generator": self._generator(torch, seed),
            },
        )
        result = pipeline(**arguments)
        images = getattr(result, "images", None)
        if not images:
            raise RuntimeError("FLUX returned no image")
        output = Path(output_dir) / f"{uuid4().hex}.png"
        output.parent.mkdir(parents=True, exist_ok=True)
        images[0].save(output)
        return FluxArtifact(str(output), width, height)

    generate_image = generate

    def status(self) -> dict[str, Any]:
        gpu = gpu_runtime.detect_gpu()
        return {
            "model": FLUX_LABEL,
            "loaded": self.loaded,
            "gpu": bool(gpu.get("available")),
        }


# Constructing the singleton is cheap; model weights are still loaded only by
# ``load``/``generate``.  Keeping a named instance also makes worker wiring and
# operational introspection straightforward.
flux_runtime = FluxRuntime()


def get_flux_runtime() -> FluxRuntime:
    return flux_runtime


__all__ = ["FLUX_MODEL_ID", "FluxArtifact", "FluxRuntime", "flux_runtime", "get_flux_runtime"]
