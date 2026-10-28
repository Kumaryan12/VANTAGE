import base64
import hashlib
import os
import re
import tempfile
from pathlib import Path

from app.core.config import settings
from app.core.errors import AppError

KEY = re.compile(r"^[a-f0-9]{64}/[a-f0-9-]{36}$")
CATEGORIES = {"model", "document", "dataset", "report", "export"}
MAX_OBJECT_BYTES = 12 * 1024 * 1024


def validate_key(key, category):
    if not isinstance(key, str) or not KEY.fullmatch(key) or category not in CATEGORIES:
        raise AppError("STORAGE_KEY", "Invalid server-generated private object reference.", 403)


def local_root(category):
    config = settings()
    return Path(
        config.model_artifact_dir
        if category == "model"
        else config.document_storage_dir
        if category == "document"
        else config.private_storage_dir
    ).resolve()


class LocalStorage:
    name = "local"

    def path(self, key, category):
        validate_key(key, category)
        root = local_root(category)
        path = (root / key).resolve()
        if not path.is_relative_to(root):
            raise AppError("STORAGE_PATH", "Private object escaped its storage root.", 403)
        return path

    def put(self, key, category, data):
        path = self.path(key, category)
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if path.exists():
            raise AppError("STORAGE_IMMUTABLE", "Private objects cannot be overwritten.", 409)
        fd, temporary = tempfile.mkstemp(prefix=".staged-", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            # Link publishes atomically with no overwrite, unlike replace against an existing ID.
            os.link(temporary, path)
        except FileExistsError:
            raise AppError(
                "STORAGE_IMMUTABLE", "Private objects cannot be overwritten.", 409
            ) from None
        finally:
            Path(temporary).unlink(missing_ok=True)

    def get(self, key, category, limit=MAX_OBJECT_BYTES):
        path = self.path(key, category)
        try:
            if path.stat().st_size > limit:
                raise AppError("STORAGE_SIZE", "Private object exceeds its size contract.", 409)
            fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(fd, "rb") as file:
                data = file.read(limit + 1)
        except OSError:
            raise AppError("STORAGE_UNAVAILABLE", "Private object is unavailable.", 409) from None
        if len(data) > limit:
            raise AppError("STORAGE_SIZE", "Private object exceeds its size contract.", 409)
        return data

    def delete(self, key, category):
        self.path(key, category).unlink(missing_ok=True)


class S3Storage:
    name = "s3"

    def __init__(self, client=None):
        import boto3
        from botocore.config import Config

        config = settings()
        if not config.s3_bucket:
            raise AppError(
                "STORAGE_CONFIGURATION", "An explicit private object-store bucket is required.", 503
            )
        self.bucket = config.s3_bucket
        self.client = client or boto3.client(
            "s3",
            region_name=config.s3_region,
            endpoint_url=config.s3_endpoint_url or None,
            config=Config(connect_timeout=3, read_timeout=10, retries={"max_attempts": 2}),
        )

    def put(self, key, category, data):
        validate_key(key, category)
        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=f"{category}/{key}",
                Body=data,
                IfNoneMatch="*",
                ServerSideEncryption="AES256",
                ChecksumSHA256=base64.b64encode(hashlib.sha256(data).digest()).decode(),
            )
        except Exception:
            raise AppError(
                "STORAGE_UNAVAILABLE", "Private object upload was not confirmed.", 503
            ) from None

    def get(self, key, category, limit=MAX_OBJECT_BYTES):
        validate_key(key, category)
        try:
            result = self.client.get_object(Bucket=self.bucket, Key=f"{category}/{key}")
            body = result["Body"]
            try:
                if result["ContentLength"] > limit:
                    raise ValueError()
                data = body.read(limit + 1)
                if len(data) > limit:
                    raise ValueError()
                return data
            finally:
                body.close()
        except Exception:
            raise AppError(
                "STORAGE_UNAVAILABLE", "Private object is unavailable or oversized.", 409
            ) from None

    def delete(self, key, category):
        validate_key(key, category)
        try:
            self.client.delete_object(Bucket=self.bucket, Key=f"{category}/{key}")
        except Exception:
            raise AppError(
                "STORAGE_UNAVAILABLE", "Private object deletion was not confirmed.", 503
            ) from None


def backend(name=None):
    name = name or settings().storage_backend
    if name == "local":
        return LocalStorage()
    if name == "s3":
        return S3Storage()
    raise AppError("STORAGE_CONFIGURATION", "Unknown private storage backend.", 503)
