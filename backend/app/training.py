"""Dataset preparation and execution boundary for LoRA training."""
import json
import shlex
import subprocess
from pathlib import Path
from uuid import UUID

from .core.config import settings
from .db import SessionLocal
from .models import Asset
from .storage import storage


class TrainingError(RuntimeError):
    pass


def prepare_dataset(persona_id: UUID, asset_ids: list[UUID], identity: str, style: str) -> Path:
    if not 20 <= len(asset_ids) <= 50:
        raise TrainingError("LoRA training requires between 20 and 50 reference assets")
    dataset_dir = Path(settings.local_media_dir) / "datasets" / str(persona_id)
    dataset_dir.mkdir(parents=True, exist_ok=True)
    manifest = dataset_dir / "metadata.jsonl"
    with SessionLocal() as db, manifest.open("w", encoding="utf-8") as output:
        for index, asset_id in enumerate(asset_ids, start=1):
            asset = db.get(Asset, str(asset_id))
            if not asset:
                raise TrainingError(f"Reference asset not found: {asset_id}")
            if asset.kind != "image":
                raise TrainingError(f"Reference asset is not an image: {asset.name}")
            if settings.storage_enabled:
                raise TrainingError("MinIO dataset download is required before local training")
            source = storage.local_path(asset.object_key)
            if not source.is_file():
                raise TrainingError(f"Reference file is missing: {asset.name}")
            target = dataset_dir / f"{index:03d}{source.suffix.lower()}"
            target.write_bytes(source.read_bytes())
            output.write(json.dumps({"file_name": target.name, "text": f"photo of {identity}, {style}, identity reference {index}"}) + "\n")
    return dataset_dir


def execute_training(dataset_dir: Path, output_dir: Path) -> Path:
    if not settings.training_enabled:
        raise TrainingError("LoRA training is disabled; set BROBOND_TRAINING_ENABLED=true on a GPU worker")
    if not settings.lora_trainer_command:
        raise TrainingError("BROBOND_LORA_TRAINER_COMMAND is not configured")
    output_dir.mkdir(parents=True, exist_ok=True)
    command = shlex.split(settings.lora_trainer_command) + ["--dataset", str(dataset_dir), "--output", str(output_dir)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=86400)
    if result.returncode != 0:
        raise TrainingError(result.stderr[-2000:] or "LoRA trainer failed")
    outputs = sorted(output_dir.glob("*.safetensors"))
    if not outputs:
        raise TrainingError("Trainer finished without producing a safetensors file")
    return outputs[-1]
