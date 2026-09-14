"""CLI preflight for the real inference/training host."""
import json
import shutil
import subprocess
import sys


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def main() -> int:
    checks = {"nvidia-smi": command_exists("nvidia-smi"), "ffmpeg": command_exists("ffmpeg"), "docker": command_exists("docker")}
    if checks["nvidia-smi"]:
        try:
            checks["nvidia_smi_output"] = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"], capture_output=True, text=True, timeout=5, check=True).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            checks["nvidia_smi_output"] = "unavailable"
    print(json.dumps(checks, indent=2))
    required = ["nvidia-smi", "ffmpeg"]
    return 0 if all(checks[item] for item in required) else 1


if __name__ == "__main__":
    sys.exit(main())
