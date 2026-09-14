"""Optional Wan/Hunyuan video provider boundary.

The worker owns orchestration; this adapter owns model-specific inference.
Install the video GPU profile before enabling it on a CUDA worker.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class VideoGenerationOutput:
    path: str
    duration_seconds: int
    fps: int


class VideoProvider:
    def generate(self, prompt: str, parameters: dict[str, Any], output_dir: str) -> VideoGenerationOutput:
        raise NotImplementedError


class WanVideoProvider(VideoProvider):
    def __init__(self, model_id: str = "Wan-AI/Wan2.1-T2V-1.3B-Diffusers") -> None:
        self.model_id = model_id
        self._pipeline = None

    def _load(self):
        if self._pipeline is None:
            try:
                import torch
                from diffusers import WanPipeline
            except ImportError as error:
                raise RuntimeError("Video GPU dependencies are not installed") from error
            if not torch.cuda.is_available():
                raise RuntimeError("CUDA GPU is required for the Wan provider")
            self._pipeline = WanPipeline.from_pretrained(self.model_id, torch_dtype=torch.bfloat16)
            self._pipeline.to("cuda")
        return self._pipeline

    def generate(self, prompt: str, parameters: dict[str, Any], output_dir: str) -> VideoGenerationOutput:
        pipeline = self._load()
        fps = int(parameters.get("fps", 24))
        duration = int(parameters.get("duration_seconds", 5))
        width, height = _dimensions(parameters.get("aspect_ratio", "16:9"))
        result = pipeline(prompt=prompt, num_frames=fps * duration, width=width, height=height).frames[0]
        output = Path(output_dir) / "video.mp4"
        output.parent.mkdir(parents=True, exist_ok=True)
        try:
            import imageio.v3 as iio
            iio.imwrite(output, result, fps=fps, codec="libx264")
        except ImportError as error:
            raise RuntimeError("imageio and imageio-ffmpeg are required for video encoding") from error
        return VideoGenerationOutput(str(output), duration, fps)


def _dimensions(aspect_ratio: str) -> tuple[int, int]:
    return {"16:9": (832, 480), "9:16": (480, 832), "1:1": (512, 512)}.get(aspect_ratio, (832, 480))
