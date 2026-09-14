"""Storage abstraction for local development and MinIO deployments."""
from pathlib import Path
from uuid import uuid4

import boto3
from botocore.client import Config
from fastapi import UploadFile

from .core.config import settings


class StorageService:
    def __init__(self) -> None:
        self.local_root = Path(settings.local_media_dir)
        self.local_root.mkdir(parents=True, exist_ok=True)
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.minio_endpoint,
            aws_access_key_id=settings.minio_access_key,
            aws_secret_access_key=settings.minio_secret_key,
            config=Config(signature_version="s3v4"),
            region_name="us-east-1",
        )

    def _key(self, filename: str, workspace_id: str) -> str:
        safe_name = Path(filename or "upload.bin").name.replace(" ", "-")
        return f"{workspace_id}/{uuid4()}-{safe_name}"

    async def save(self, file: UploadFile, workspace_id: str) -> tuple[str, str]:
        key = self._key(file.filename or "upload.bin", workspace_id)
        if settings.storage_enabled:
            self.client.upload_fileobj(file.file, settings.minio_bucket, key, ExtraArgs={"ContentType": file.content_type or "application/octet-stream"})
            return key, self.client.generate_presigned_url("get_object", Params={"Bucket": settings.minio_bucket, "Key": key}, ExpiresIn=3600)
        destination = self.local_root / key
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(await file.read())
        return key, f"/api/v1/assets/download/{key}"

    def signed_url(self, key: str) -> str:
        if settings.storage_enabled:
            return self.client.generate_presigned_url("get_object", Params={"Bucket": settings.minio_bucket, "Key": key}, ExpiresIn=3600)
        return f"/api/v1/assets/download/{key}"

    def local_path(self, key: str) -> Path:
        root = self.local_root.resolve()
        path = (root / key).resolve()
        if root not in path.parents:
            raise ValueError("Invalid asset path")
        return path


storage = StorageService()
