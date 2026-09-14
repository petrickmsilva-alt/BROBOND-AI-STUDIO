"""Runtime capability detection for the local GPU worker."""
import shutil
import subprocess


def gpu_info() -> dict:
    if not shutil.which("nvidia-smi"):
        return {"available": False, "backend": "cpu", "message": "nvidia-smi not found"}
    try:
        output = subprocess.check_output(["nvidia-smi", "--query-gpu=name,memory.total,memory.free,driver_version", "--format=csv,noheader,nounits"], text=True, timeout=3).strip()
        rows = []
        for line in output.splitlines():
            name, total, free, driver = [part.strip() for part in line.split(",")]
            rows.append({"name": name, "vram_total_mb": int(float(total)), "vram_free_mb": int(float(free)), "driver": driver})
        return {"available": bool(rows), "backend": "cuda", "gpus": rows}
    except (OSError, subprocess.SubprocessError, ValueError):
        return {"available": False, "backend": "cpu", "message": "GPU detection failed"}
