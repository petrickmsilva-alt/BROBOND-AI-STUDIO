"""FLUX/Diffusers image provider.

Diffusers is optional so the orchestration API can run on CPU-only machines.
Install the GPU profile before enabling real inference:
`pip install torch diffusers transformers accelerate safetensors`.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class GenerationOutput:
    path: str
    width: int
    height: int


class ImageProvider:
    def generate(self, prompt: str, parameters: dict[str, Any], output_dir: str) -> GenerationOutput:
        raise NotImplementedError


class FluxDiffusersProvider(ImageProvider):
    def __init__(self, model_id: str = "black-forest-labs/FLUX.1-dev") -> None:
        self.model_id = model_id
        self._pipeline = None

    def _load(self):
        if self._pipeline is None:
            try:
                import torch
                from diffusers import FluxPipeline
            except ImportError as error:
                raise RuntimeError("Diffusers GPU dependencies are not installed") from error
            if not torch.cuda.is_available():
                raise RuntimeError("CUDA GPU is required for the FLUX provider")
            self._pipeline = FluxPipeline.from_pretrained(self.model_id, torch_dtype=torch.bfloat16)
            self._pipeline.enable_model_cpu_offload()
        return self._pipeline

    def _apply_lora(self, pipeline, lora_path: str | None) -> None:
        if lora_path:
            pipeline.load_lora_weights(lora_path, adapter_name="brobond_persona")
            pipeline.set_adapters(["brobond_persona"], adapter_weights=[1.0])

    def _apply_conditioning(self, pipeline, parameters: dict[str, Any]) -> None:
        controlnet = parameters.get("controlnet", "none")
        if controlnet != "none":
            raise RuntimeError(f"ControlNet '{controlnet}' requires a ControlNet-specific pipeline variant")
        reference_path = parameters.get("reference_path")
        if reference_path:
            if not hasattr(pipeline, "load_ip_adapter"):
                raise RuntimeError("Current image pipeline does not support IP Adapter")
            pipeline.load_ip_adapter("h94/IP-Adapter", weight_name="ip-adapter-plus_sdxl_vit-h.safetensors")
            pipeline.set_ip_adapter_scale(float(parameters.get("ip_adapter_scale", 0.7)))

    def generate(self, prompt: str, parameters: dict[str, Any], output_dir: str) -> GenerationOutput:
        pipeline = self._load()
        self._apply_lora(pipeline, parameters.get("lora_path"))
        self._apply_conditioning(pipeline, parameters)
        width, height = _dimensions(parameters.get("aspect_ratio", "16:9"), int(parameters.get("resolution", 1024)))
        image = pipeline(
            prompt=prompt,
            negative_prompt=parameters.get("negative_prompt", ""),
            width=width,
            height=height,
            guidance_scale=float(parameters.get("guidance_scale", 7.5)),
            num_inference_steps=int(parameters.get("steps", 28)),
            generator=_generator(parameters.get("seed")),
        ).images[0]
        path = Path(output_dir) / "image.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path)
        return GenerationOutput(str(path), width, height)


def _generator(seed: int | None):
    if seed is None:
        return None
    import torch
    return torch.Generator(device="cuda").manual_seed(seed)


def _dimensions(aspect_ratio: str, resolution: int) -> tuple[int, int]:
    ratios = {"16:9": (16, 9), "1:1": (1, 1), "9:16": (9, 16), "4:3": (4, 3), "3:4": (3, 4)}
    width_ratio, height_ratio = ratios.get(aspect_ratio, (16, 9))
    if width_ratio >= height_ratio:
        width = resolution
        height = round(resolution * height_ratio / width_ratio / 8) * 8
    else:
        height = resolution
        width = round(resolution * width_ratio / height_ratio / 8) * 8
    return width, height
