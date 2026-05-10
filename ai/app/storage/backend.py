"""
Atopsy — Storage Backend Abstraction.

Provides a unified interface for persisting evidence files,
with pluggable backends (local filesystem, S3-compatible).
All paths are UUID-based to prevent path traversal and collisions.
"""

from __future__ import annotations

import os
import shutil
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import BinaryIO

from app.core.config import settings
from app.core.logger import logger
from app.exceptions.pipeline import StorageError


class StorageBackend(ABC):
    """Abstract storage backend protocol."""

    @abstractmethod
    def save(
        self,
        file_obj: BinaryIO,
        category: str,
        original_filename: str,
    ) -> dict:
        """
        Persist a file and return storage metadata.

        Returns:
            dict with keys: storage_key, storage_path, size_bytes
        """
        ...

    @abstractmethod
    def retrieve(self, storage_key: str) -> Path | str:
        """Return the local path or a signed URL for the stored file."""
        ...

    @abstractmethod
    def delete(self, storage_key: str) -> bool:
        """Remove a file from storage. Returns True if deleted."""
        ...

    @abstractmethod
    def exists(self, storage_key: str) -> bool:
        """Check if a file exists in storage."""
        ...


class LocalStorageBackend(StorageBackend):
    """
    Local filesystem storage.

    Layout: {root}/{category}/{date}/{uuid}.{ext}
    """

    def __init__(self, root: str | None = None) -> None:
        self.root = Path(root or settings.STORAGE_ROOT)
        self.root.mkdir(parents=True, exist_ok=True)
        logger.info(f"LocalStorage initialized at {self.root.resolve()}")

    def save(
        self,
        file_obj: BinaryIO,
        category: str,
        original_filename: str,
    ) -> dict:
        try:
            from datetime import datetime, timezone

            date_prefix = datetime.now(timezone.utc).strftime("%Y/%m/%d")
            ext = Path(original_filename).suffix.lower() or ".bin"

            # Sanitize: UUID-based name prevents path traversal
            file_uuid = str(uuid.uuid4())
            storage_key = f"{category}/{date_prefix}/{file_uuid}{ext}"
            full_path = self.root / storage_key

            full_path.parent.mkdir(parents=True, exist_ok=True)

            size = 0
            with open(full_path, "wb") as dest:
                while chunk := file_obj.read(
                    settings.PIPELINE_CHUNK_SIZE
                ):
                    dest.write(chunk)
                    size += len(chunk)

            logger.info(
                f"Stored file: {storage_key} ({size} bytes)"
            )

            return {
                "storage_key": storage_key,
                "storage_path": str(full_path.resolve()),
                "size_bytes": size,
            }

        except OSError as exc:
            raise StorageError(
                f"Failed to save file: {exc}",
                context={"original_filename": original_filename},
            ) from exc

    def retrieve(self, storage_key: str) -> Path:
        full_path = self.root / storage_key
        if not full_path.exists():
            raise StorageError(
                "File not found in storage",
                context={"storage_key": storage_key},
            )
        return full_path

    def delete(self, storage_key: str) -> bool:
        full_path = self.root / storage_key
        if full_path.exists():
            full_path.unlink()
            logger.info(f"Deleted file: {storage_key}")
            return True
        return False

    def exists(self, storage_key: str) -> bool:
        return (self.root / storage_key).exists()


class S3StorageBackend(StorageBackend):
    """
    S3-compatible storage backend (AWS S3, MinIO, etc.).

    Requires boto3. Falls back to LocalStorageBackend
    if credentials are not configured.
    """

    def __init__(self) -> None:
        try:
            import boto3
            from botocore.config import Config as BotoConfig

            self.bucket = settings.S3_BUCKET
            self.client = boto3.client(
                "s3",
                endpoint_url=settings.S3_ENDPOINT_URL or None,
                aws_access_key_id=settings.S3_ACCESS_KEY,
                aws_secret_access_key=settings.S3_SECRET_KEY,
                region_name=settings.S3_REGION,
                config=BotoConfig(
                    retries={"max_attempts": 3, "mode": "adaptive"}
                ),
            )
            logger.info(
                f"S3Storage initialized: bucket={self.bucket}"
            )
        except ImportError:
            raise StorageError(
                "boto3 is required for S3 storage backend. "
                "Install with: pip install boto3"
            )

    def save(
        self,
        file_obj: BinaryIO,
        category: str,
        original_filename: str,
    ) -> dict:
        from datetime import datetime, timezone

        date_prefix = datetime.now(timezone.utc).strftime("%Y/%m/%d")
        ext = Path(original_filename).suffix.lower() or ".bin"
        file_uuid = str(uuid.uuid4())
        storage_key = f"{category}/{date_prefix}/{file_uuid}{ext}"

        try:
            self.client.upload_fileobj(file_obj, self.bucket, storage_key)

            head = self.client.head_object(
                Bucket=self.bucket, Key=storage_key
            )
            size = head.get("ContentLength", 0)

            logger.info(
                f"S3 stored: s3://{self.bucket}/{storage_key} ({size} bytes)"
            )

            return {
                "storage_key": storage_key,
                "storage_path": f"s3://{self.bucket}/{storage_key}",
                "size_bytes": size,
            }

        except Exception as exc:
            raise StorageError(
                f"S3 upload failed: {exc}",
                context={"storage_key": storage_key},
            ) from exc

    def retrieve(self, storage_key: str) -> str:
        """Return a pre-signed URL valid for 1 hour."""
        try:
            url = self.client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self.bucket,
                    "Key": storage_key,
                },
                ExpiresIn=3600,
            )
            return url
        except Exception as exc:
            raise StorageError(
                f"Failed to generate signed URL: {exc}",
                context={"storage_key": storage_key},
            ) from exc

    def delete(self, storage_key: str) -> bool:
        try:
            self.client.delete_object(
                Bucket=self.bucket, Key=storage_key
            )
            return True
        except Exception:
            return False

    def exists(self, storage_key: str) -> bool:
        try:
            self.client.head_object(
                Bucket=self.bucket, Key=storage_key
            )
            return True
        except Exception:
            return False


def get_storage_backend() -> StorageBackend:
    """Factory: return the configured storage backend."""
    if settings.STORAGE_BACKEND == "s3" and settings.S3_BUCKET:
        return S3StorageBackend()
    return LocalStorageBackend()
