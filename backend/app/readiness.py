"""Preflight checks for a real local GPU worker."""
import importlib.util
import shutil

from .system import gpu_info


def readiness() -> dict:
    gpu = gpu_info()
    checks = {
        "cuda": bool(gpu.get("available")),
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "redis_client": importlib.util.find_spec("redis") is not None,
        "diffusers": importlib.util.find_spec("diffusers") is not None,
        "torch": importlib.util.find_spec("torch") is not None,
        "pillow": importlib.util.find_spec("PIL") is not None,
        "celery": importlib.util.find_spec("celery") is not None,
    }
    inference_ready = checks["cuda"] and checks["diffusers"] and checks["torch"]
    media_ready = checks["ffmpeg"]
    return {"ready": inference_ready and media_ready, "inference_ready": inference_ready, "media_ready": media_ready, "checks": checks, "gpu": gpu}
