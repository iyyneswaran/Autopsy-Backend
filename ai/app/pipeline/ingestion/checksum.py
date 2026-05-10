"""
Atopsy — File Checksum & Deduplication Engine.

Computes SHA-256 and MD5 hashes for evidence files.
Provides fast O(1) duplicate detection via the FileChecksum table.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import BinaryIO

from app.core.config import settings
from app.core.logger import logger


class ChecksumResult:
    """Holds computed checksum values."""

    __slots__ = ("sha256", "md5", "size_bytes")

    def __init__(
        self, sha256: str, md5: str, size_bytes: int
    ) -> None:
        self.sha256 = sha256
        self.md5 = md5
        self.size_bytes = size_bytes

    def __repr__(self) -> str:
        return (
            f"ChecksumResult(sha256={self.sha256[:16]}..., "
            f"size={self.size_bytes})"
        )


def compute_checksums_from_file(
    file_path: str | Path,
    chunk_size: int | None = None,
) -> ChecksumResult:
    """Compute SHA-256 and MD5 checksums from a file on disk."""

    chunk_size = chunk_size or settings.PIPELINE_CHUNK_SIZE
    sha256 = hashlib.sha256()
    md5 = hashlib.md5()
    size = 0

    with open(file_path, "rb") as f:
        while chunk := f.read(chunk_size):
            sha256.update(chunk)
            md5.update(chunk)
            size += len(chunk)

    result = ChecksumResult(
        sha256=sha256.hexdigest(),
        md5=md5.hexdigest(),
        size_bytes=size,
    )

    logger.debug(f"Computed checksums: {result}")
    return result


def compute_checksums_from_stream(
    stream: BinaryIO,
    chunk_size: int | None = None,
) -> ChecksumResult:
    """Compute checksums from a file-like stream (without seeking back)."""

    chunk_size = chunk_size or settings.PIPELINE_CHUNK_SIZE
    sha256 = hashlib.sha256()
    md5 = hashlib.md5()
    size = 0

    while chunk := stream.read(chunk_size):
        sha256.update(chunk)
        md5.update(chunk)
        size += len(chunk)

    return ChecksumResult(
        sha256=sha256.hexdigest(),
        md5=md5.hexdigest(),
        size_bytes=size,
    )


def check_duplicate(
    sha256: str, db_session
) -> dict | None:
    """
    Check if a file with the same SHA-256 already exists.

    Returns the existing FileChecksum row as dict, or None.
    """
    from app.models.pipeline import FileChecksum

    existing = (
        db_session.query(FileChecksum)
        .filter(FileChecksum.sha256 == sha256)
        .first()
    )

    if existing:
        logger.info(
            f"Duplicate detected: sha256={sha256[:16]}... "
            f"evidence_id={existing.evidence_file_id}"
        )
        return {
            "evidence_file_id": str(existing.evidence_file_id),
            "sha256": existing.sha256,
        }

    return None
