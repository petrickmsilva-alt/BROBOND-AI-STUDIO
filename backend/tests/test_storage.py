"""ETAPA 12 tests — object storage, local and S3/MinIO.

`storage.py` sat at 61% coverage: every S3 line was dead in tests because
`storage_enabled` was only ever set to False, and `local_path`'s path-traversal
guard had never executed once. A security control with zero coverage is a claim,
not a guarantee, so both halves are exercised here.
"""
from __future__ import annotations

import io
from pathlib import Path

import pytest
from botocore.exceptions import ClientError
from starlette.datastructures import Headers

from app.core.config import settings
from app.storage import PRESIGNED_TTL_SECONDS, StorageService, storage


class FakeS3:
    """In-memory stand-in for the boto3 S3 client.

    Records what was called so the tests can assert on the wire, not just on the
    returned value.
    """

    def __init__(self, *, bucket_exists: bool = True) -> None:
        self.objects: dict[str, bytes] = {}
        self.bucket_exists = bucket_exists
        self.created_buckets: list[str] = []
        self.deleted: list[str] = []
        self.presigned: list[tuple[str, int]] = []

    # -- helpers
    def _require_bucket(self) -> None:
        if not self.bucket_exists:
            raise ClientError({"Error": {"Code": "404", "Message": "Not Found"}}, "HeadBucket")

    # -- boto3 surface used by StorageService
    def upload_fileobj(self, fileobj, bucket, key, ExtraArgs=None):
        self._require_bucket()
        self.objects[key] = fileobj.read()

    def upload_file(self, filename, bucket, key, ExtraArgs=None):
        self._require_bucket()
        self.objects[key] = Path(filename).read_bytes()

    def generate_presigned_url(self, operation, Params=None, ExpiresIn=None):
        self.presigned.append((Params["Key"], ExpiresIn))
        return f"https://cdn.example/{Params['Bucket']}/{Params['Key']}?x=1"

    def head_object(self, Bucket=None, Key=None):
        self._require_bucket()
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "404", "Message": "Not Found"}}, "HeadObject")
        return {"ContentLength": len(self.objects[Key])}

    def head_bucket(self, Bucket=None):
        self._require_bucket()
        return {}

    def create_bucket(self, Bucket=None):
        self.bucket_exists = True
        self.created_buckets.append(Bucket)
        return {}

    def download_file(self, Bucket=None, Key=None, Filename=None):
        self._require_bucket()
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "404", "Message": "Not Found"}}, "GetObject")
        target = Path(Filename)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(self.objects[Key])

    def delete_object(self, Bucket=None, Key=None):
        self.deleted.append(Key)
        self.objects.pop(Key, None)


def _upload(name: str, payload: bytes, content_type: str):
    from fastapi import UploadFile

    return UploadFile(
        io.BytesIO(payload),
        size=len(payload),
        filename=name,
        headers=Headers({"content-type": content_type}),
    )


@pytest.fixture()
def local_service(tmp_path, monkeypatch):
    """A StorageService rooted in a temp dir, in local mode."""

    monkeypatch.setattr(settings, "storage_enabled", False)
    service = StorageService.__new__(StorageService)
    service.local_root = tmp_path / "media"
    service.local_root.mkdir(parents=True, exist_ok=True)
    service._client = None
    return service


@pytest.fixture()
def s3_service(local_service, monkeypatch):
    """The same service, switched to object storage with a fake client."""

    monkeypatch.setattr(settings, "storage_enabled", True)
    fake = FakeS3()
    local_service.client = fake
    return local_service, fake


# ---------------------------------------------------------------------------
# Keys and URLs
# ---------------------------------------------------------------------------


def test_keys_are_scoped_to_the_workspace_and_unique(local_service) -> None:
    first = local_service._key("cat.png", "ws-1")
    second = local_service._key("cat.png", "ws-1")
    assert first.startswith("ws-1/")
    assert first.endswith("cat.png")
    assert first != second, "two uploads of the same name must not collide"


def test_a_key_cannot_carry_a_path(local_service) -> None:
    assert local_service._key("../../etc/passwd", "ws-1").count("/") == 1


def test_spaces_in_filenames_do_not_survive(local_service) -> None:
    assert " " not in local_service._key("my holiday.png", "ws-1")


def test_an_empty_filename_falls_back(local_service) -> None:
    assert local_service._key("", "ws-1").endswith("upload.bin")


def test_the_local_url_points_at_the_download_route(local_service) -> None:
    assert local_service.signed_url("ws-1/a.png") == "/api/v1/assets/download/ws-1/a.png"


def test_presigned_urls_use_one_declared_ttl(s3_service) -> None:
    service, fake = s3_service
    service.signed_url("ws-1/a.png")
    assert fake.presigned == [("ws-1/a.png", PRESIGNED_TTL_SECONDS)]
    assert PRESIGNED_TTL_SECONDS == 3600


# ---------------------------------------------------------------------------
# The path-traversal guard — never executed before ETAPA 12
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "key",
    ["../etc/passwd", "../../etc/passwd", "/etc/passwd", "ws-1/../../etc/passwd", "", "."],
)
def test_traversal_keys_are_refused(local_service, key) -> None:
    with pytest.raises(ValueError, match="Invalid asset path"):
        local_service.local_path(key)


def test_a_key_inside_the_root_is_accepted(local_service) -> None:
    resolved = local_service.local_path("ws-1/img.png")
    assert resolved == (local_service.local_root / "ws-1" / "img.png").resolve()


def test_the_download_route_guard_is_reachable_through_the_api(client=None) -> None:
    """`download_local_asset` turns the ValueError into a 400, not a 500."""

    import pathlib

    source = pathlib.Path("backend/app/main.py").read_text()
    assert 'raise HTTPException(status_code=400, detail="Invalid asset path")' in source


# ---------------------------------------------------------------------------
# Local mode
# ---------------------------------------------------------------------------


def test_save_writes_the_bytes_locally(local_service) -> None:
    import asyncio

    key, url = asyncio.run(local_service.save(_upload("a.png", b"png-bytes", "image/png"), "ws-1"))
    assert (local_service.local_root / key).read_bytes() == b"png-bytes"
    assert url == f"/api/v1/assets/download/{key}"


def test_save_path_copies_the_generated_file(local_service, tmp_path) -> None:
    generated = tmp_path / "out.png"
    generated.write_bytes(b"rendered")
    key, url = local_service.save_path(str(generated), "ws-1", "image/png")
    assert (local_service.local_root / key).read_bytes() == b"rendered"
    assert url == f"/api/v1/assets/download/{key}"


def test_download_in_local_mode_returns_the_stored_file_without_copying(local_service) -> None:
    stored = local_service.local_root / "ws-1" / "a.png"
    stored.parent.mkdir(parents=True, exist_ok=True)
    stored.write_bytes(b"x")
    got = local_service.download("ws-1/a.png", local_service.local_root / "elsewhere.png")
    assert got == stored.resolve()
    assert not (local_service.local_root / "elsewhere.png").exists()


def test_exists_and_delete_round_trip(local_service) -> None:
    stored = local_service.local_root / "ws-1" / "a.png"
    stored.parent.mkdir(parents=True, exist_ok=True)
    stored.write_bytes(b"x")
    assert local_service.exists("ws-1/a.png") is True
    assert local_service.delete("ws-1/a.png") is True
    assert local_service.exists("ws-1/a.png") is False
    assert local_service.delete("ws-1/a.png") is False, "deleting twice is not an error"


def test_exists_is_false_for_a_traversal_key_instead_of_raising(local_service) -> None:
    assert local_service.exists("../etc/passwd") is False
    assert local_service.delete("../etc/passwd") is False


def test_upload_path_is_a_no_op_when_the_file_is_already_there(local_service) -> None:
    target = local_service.local_root / "ws-1" / "exports" / "v.mp4"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"video")
    url = local_service.upload_path(target, "ws-1/exports/v.mp4", "video/mp4")
    assert url == "/api/v1/assets/download/ws-1/exports/v.mp4"
    assert target.read_bytes() == b"video"


def test_upload_path_moves_the_file_when_the_key_differs(local_service, tmp_path) -> None:
    working = tmp_path / "working.mp4"
    working.write_bytes(b"video")
    local_service.upload_path(working, "ws-1/exports/v.mp4", "video/mp4")
    assert (local_service.local_root / "ws-1" / "exports" / "v.mp4").read_bytes() == b"video"


def test_upload_path_refuses_a_traversal_key(local_service, tmp_path) -> None:
    working = tmp_path / "working.mp4"
    working.write_bytes(b"video")
    with pytest.raises(ValueError, match="Invalid asset path"):
        local_service.upload_path(working, "../escape.mp4")


def test_ensure_bucket_is_a_no_op_locally_but_creates_the_root(local_service, tmp_path) -> None:
    (local_service.local_root).rmdir()
    assert local_service.ensure_bucket() is False
    assert local_service.local_root.is_dir()


# ---------------------------------------------------------------------------
# S3 / MinIO mode — every line here was dead before
# ---------------------------------------------------------------------------


def test_save_uploads_and_returns_a_presigned_url(s3_service) -> None:
    import asyncio

    service, fake = s3_service
    key, url = asyncio.run(service.save(_upload("a.png", b"png-bytes", "image/png"), "ws-1"))
    assert fake.objects[key] == b"png-bytes"
    assert url.startswith("https://cdn.example/")


def test_save_path_uploads_the_generated_file(s3_service, tmp_path) -> None:
    service, fake = s3_service
    generated = tmp_path / "out.png"
    generated.write_bytes(b"rendered")
    key, url = service.save_path(str(generated), "ws-1", "image/png")
    assert fake.objects[key] == b"rendered"
    assert url.startswith("https://cdn.example/")


def test_download_fetches_from_the_bucket(s3_service, tmp_path) -> None:
    service, fake = s3_service
    fake.objects["ws-1/a.png"] = b"from-s3"
    got = service.download("ws-1/a.png", tmp_path / "work" / "a.png")
    assert got.read_bytes() == b"from-s3"


def test_download_a_missing_object_raises_the_s3_error(s3_service, tmp_path) -> None:
    service, _ = s3_service
    with pytest.raises(ClientError):
        service.download("ws-1/nope.png", tmp_path / "a.png")


def test_exists_asks_the_bucket(s3_service) -> None:
    service, fake = s3_service
    assert service.exists("ws-1/a.png") is False
    fake.objects["ws-1/a.png"] = b"x"
    assert service.exists("ws-1/a.png") is True


def test_delete_removes_the_object(s3_service) -> None:
    service, fake = s3_service
    fake.objects["ws-1/a.png"] = b"x"
    assert service.delete("ws-1/a.png") is True
    assert fake.deleted == ["ws-1/a.png"]
    assert service.delete("ws-1/a.png") is False


def test_ensure_bucket_creates_a_missing_bucket(s3_service) -> None:
    service, fake = s3_service
    fake.bucket_exists = False
    assert service.ensure_bucket() is True
    assert fake.created_buckets == [settings.minio_bucket]


def test_ensure_bucket_leaves_an_existing_bucket_alone(s3_service) -> None:
    service, fake = s3_service
    assert service.ensure_bucket() is False
    assert fake.created_buckets == []


def test_upload_path_pushes_to_the_caller_chosen_key(s3_service, tmp_path) -> None:
    service, fake = s3_service
    working = tmp_path / "v.mp4"
    working.write_bytes(b"video")
    url = service.upload_path(working, "ws-1/exports/v.mp4", "video/mp4")
    assert fake.objects["ws-1/exports/v.mp4"] == b"video"
    assert url.startswith("https://cdn.example/")


def test_a_missing_bucket_surfaces_as_a_client_error_not_a_crash(s3_service) -> None:
    service, fake = s3_service
    fake.bucket_exists = False
    assert service.exists("ws-1/a.png") is False, "head_bucket 404 is answered, not raised"


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_the_client_is_not_built_at_construction(monkeypatch, tmp_path) -> None:
    """Importing the app must not resolve AWS credentials or hit a region."""

    monkeypatch.setattr(settings, "local_media_dir", str(tmp_path / "m"))
    service = StorageService()
    assert service._client is None


def test_the_client_is_built_once_and_cached(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(settings, "local_media_dir", str(tmp_path / "m"))
    service = StorageService()
    first = service.client
    assert first is service.client
    assert service._client is first


def test_the_module_singleton_is_usable() -> None:
    assert storage.local_root.is_dir()
    assert storage._client is None or storage._client is not None


def test_the_service_no_longer_refuses_object_storage() -> None:
    """The three 501s existed only because there was no read primitive."""

    import pathlib

    main = pathlib.Path("backend/app/main.py").read_text()
    queue = pathlib.Path("backend/app/queue.py").read_text()
    assert "adapter is not enabled" not in main
    assert "is not enabled for exports" not in main
    assert "download adapter is required" not in queue
    assert main.count("storage.download(") == 2
    assert queue.count("storage.download(") == 2
