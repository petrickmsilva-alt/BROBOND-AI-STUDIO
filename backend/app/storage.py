"""Storage abstraction for local development and MinIO/S3 deployments.

The public surface is unchanged from before ETAPA 12 — `save`, `save_path`,
`signed_url` and `local_path` behave exactly as they did. What ETAPA 12 adds is
the half that was missing: the service could **write** objects but had no way to
read one back, delete one, or check that one exists. Three call sites therefore
refused to run whenever `storage_enabled` was true, answering 501 with
"adapter is not enabled" — not because the feature was hard, but because
`StorageService` offered no primitive to build it on.

Everything here is S3 API, which is what MinIO speaks, so one implementation
covers both. The `minio` client package pinned in `requirements.txt` is not used.
"""
from pathlib import Path
from uuid import uuid4

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from fastapi import UploadFile

from .core.config import settings

#: Presigned URLs are short lived on purpose: they are handed to a browser for
#: one viewing, not stored. Was hardcoded as `3600` in three separate places.
PRESIGNED_TTL_SECONDS = 3600

#: Raised when an operation needs object storage but it is switched off. Callers
#: translate it into an HTTP 503 rather than leaking a stack trace.
class StorageUnavailable(RuntimeError):
    """Object storage was required but `BROBOND_STORAGE_ENABLED` is false."""


class StorageService:
    def __init__(self) -> None:
        self.local_root = Path(settings.local_media_dir)
        self.local_root.mkdir(parents=True, exist_ok=True)
        #: Built on first use. Constructing a boto3 client resolves credentials
        #: and region, which is work that should not happen at import time and
        #: makes the client injectable for tests.
        self._client = None

    # ------------------------------------------------------------------ client

    @property
    def client(self):
        """Lazily built S3 client. Assignable, so tests can inject a fake."""

        if self._client is None:
            self._client = boto3.client(
                "s3",
                endpoint_url=settings.minio_endpoint,
                aws_access_key_id=settings.minio_access_key,
                aws_secret_access_key=settings.minio_secret_key,
                config=Config(signature_version="s3v4"),
                region_name="us-east-1",
            )
        return self._client

    @client.setter
    def client(self, value) -> None:
        self._client = value

    # ------------------------------------------------------------------- keys

    def _key(self, filename: str, workspace_id: str) -> str:
        safe_name = Path(filename or "upload.bin").name.replace(" ", "-")
        return f"{workspace_id}/{uuid4()}-{safe_name}"

    # ------------------------------------------------------------------ write

    async def save(self, file: UploadFile, workspace_id: str) -> tuple[str, str]:
        key = self._key(file.filename or "upload.bin", workspace_id)
        if settings.storage_enabled:
            self.client.upload_fileobj(file.file, settings.minio_bucket, key, ExtraArgs={"ContentType": file.content_type or "application/octet-stream"})
            return key, self.client.generate_presigned_url("get_object", Params={"Bucket": settings.minio_bucket, "Key": key}, ExpiresIn=PRESIGNED_TTL_SECONDS)
        destination = self.local_root / key
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(await file.read())
        return key, f"/api/v1/assets/download/{key}"

    def save_path(self, source: str, workspace_id: str, content_type: str = "image/png") -> tuple[str, str]:
        """Persist a generated file and return its object key and access URL."""
        source_path = Path(source)
        key = self._key(source_path.name, workspace_id)
        if settings.storage_enabled:
            self.client.upload_file(str(source_path), settings.minio_bucket, key, ExtraArgs={"ContentType": content_type})
            return key, self.signed_url(key)
        destination = self.local_root / key
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source_path.read_bytes())
        return key, f"/api/v1/assets/download/{key}"

    def upload_path(self, source: str | Path, key: str, content_type: str = "application/octet-stream") -> str:
        """Upload to a **caller-chosen** key, unlike `save_path` which mints one.

        Export and conditioning derive their key from the asset they came from
        (`{workspace}/exports/{asset}-{quality}.mp4`), so it must stay stable —
        minting a UUID there would orphan the key already written to the
        `Asset` row. In local mode the working file usually already is the
        stored file, so nothing is copied.
        """

        if not settings.storage_enabled:
            target = self.local_path(key)
            source_path = Path(source).resolve()
            if source_path != target.resolve():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source_path.read_bytes())
            return f"/api/v1/assets/download/{key}"
        self.client.upload_file(str(source), settings.minio_bucket, key, ExtraArgs={"ContentType": content_type})
        return self.signed_url(key)

    # ------------------------------------------------------------------- read

    def download(self, key: str, destination: str | Path) -> Path:
        """Bring an object to a local working file and return its path.

        This is the primitive whose absence made three features answer 501 the
        moment object storage was switched on: conditioning, export and LoRA
        loading all need real bytes on a filesystem to work with.

        In local mode nothing is copied — the stored file already is a local
        file, so its path is returned directly. Callers must treat it as
        read-only, which every current caller does.
        """

        if not settings.storage_enabled:
            return self.local_path(key)
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        self.client.download_file(Bucket=settings.minio_bucket, Key=key, Filename=str(target))
        return target

    def exists(self, key: str) -> bool:
        """True when the object is actually there.

        Without this, referencing an asset that was never uploaded only fails
        later, at download time, far from the cause.
        """

        if not settings.storage_enabled:
            try:
                return self.local_path(key).is_file()
            except ValueError:
                return False
        try:
            self.client.head_object(Bucket=settings.minio_bucket, Key=key)
        except ClientError:
            return False
        return True

    def delete(self, key: str) -> bool:
        """Remove an object. Returns True when something was deleted.

        Deleting an `Asset` row never removed the bytes, so a workspace that
        cleaned itself up still filled the bucket. Local deletes are guarded by
        `local_path`, so a traversal key cannot escape the media root.
        """

        if not settings.storage_enabled:
            try:
                path = self.local_path(key)
            except ValueError:
                return False
            if not path.is_file():
                return False
            path.unlink()
            return True
        if not self.exists(key):
            return False
        self.client.delete_object(Bucket=settings.minio_bucket, Key=key)
        return True

    # ------------------------------------------------------------------ bucket

    def ensure_bucket(self) -> bool:
        """Create the bucket when it is missing. Returns True if it created it.

        A fresh MinIO instance has no `brobond-assets` bucket, and without this
        the first upload failed with a raw botocore `NoSuchBucket` that surfaced
        to the user as a 500. Idempotent: an existing bucket is left alone.
        """

        if not settings.storage_enabled:
            self.local_root.mkdir(parents=True, exist_ok=True)
            return False
        try:
            self.client.head_bucket(Bucket=settings.minio_bucket)
            return False
        except ClientError:
            pass
        self.client.create_bucket(Bucket=settings.minio_bucket)
        return True

    # -------------------------------------------------------------------- url

    def signed_url(self, key: str) -> str:
        if settings.storage_enabled:
            return self.client.generate_presigned_url("get_object", Params={"Bucket": settings.minio_bucket, "Key": key}, ExpiresIn=PRESIGNED_TTL_SECONDS)
        return f"/api/v1/assets/download/{key}"

    def local_path(self, key: str) -> Path:
        root = self.local_root.resolve()
        path = (root / key).resolve()
        if root not in path.parents:
            raise ValueError("Invalid asset path")
        return path


storage = StorageService()
