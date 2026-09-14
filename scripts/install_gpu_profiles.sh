#!/usr/bin/env bash
set -euo pipefail

if ! command -v nvidia-smi >/dev/null 2>&1; then
  echo "GPU setup blocked: nvidia-smi was not found. Install an NVIDIA driver and CUDA-compatible runtime first." >&2
  exit 1
fi

python -m pip install -r requirements-gpu.txt
python -m pip install -r requirements-video-gpu.txt
python -m pip install -r requirements-training-gpu.txt
python -m pip install -r requirements-preprocess-gpu.txt

echo "GPU profiles installed. Run: python scripts/preflight_gpu.py"
