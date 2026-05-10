"""
Atopsy — Abstract File Handler Protocol.

Defines the interface that all file-type handlers must implement.
Uses the Strategy pattern for pluggable file processing.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, BinaryIO


# MIME type → category mapping
MIME_CATEGORY_MAP: dict[str, str] = {
    # Documents
    "application/pdf": "DOCUMENT",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "DOCUMENT",
    "text/plain": "DOCUMENT",
    "text/csv": "DOCUMENT",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "DOCUMENT",
    "application/vnd.ms-excel": "DOCUMENT",
    # Images
    "image/jpeg": "IMAGE",
    "image/png": "IMAGE",
    "image/tiff": "IMAGE",
    "image/bmp": "IMAGE",
    # Video
    "video/mp4": "VIDEO",
    "video/x-msvideo": "VIDEO",
    "video/quicktime": "VIDEO",
    # Structured
    "application/json": "STRUCTURED",
}

# Extension → MIME fallback
EXTENSION_MIME_MAP: dict[str, str] = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
    ".bmp": "image/bmp",
    ".mp4": "video/mp4",
    ".avi": "video/x-msvideo",
    ".mov": "video/quicktime",
    ".json": "application/json",
}

ALLOWED_MIME_TYPES: set[str] = set(MIME_CATEGORY_MAP.keys())


def get_category_for_mime(mime_type: str) -> str | None:
    """Return the file category for a given MIME type."""
    return MIME_CATEGORY_MAP.get(mime_type)


def resolve_mime_type(
    declared_mime: str | None,
    filename: str,
) -> str | None:
    """
    Resolve MIME type from declared content-type and filename extension.
    Extension-based fallback for when the declared type is missing/generic.
    """
    from pathlib import Path

    if declared_mime and declared_mime in ALLOWED_MIME_TYPES:
        return declared_mime

    ext = Path(filename).suffix.lower()
    return EXTENSION_MIME_MAP.get(ext)


class FileHandler(ABC):
    """
    Abstract handler for a specific file category.

    Each handler knows how to:
    1. Validate the file (beyond MIME check)
    2. Extract metadata specific to that file type
    3. Pre-process the file for downstream AI layers
    """

    @property
    @abstractmethod
    def supported_mime_types(self) -> set[str]:
        """MIME types this handler can process."""
        ...

    @abstractmethod
    def validate(
        self,
        file_path: str,
        mime_type: str,
    ) -> list[str]:
        """
        Validate the file contents.

        Returns a list of warning strings. Empty list = valid.
        Raises FileValidationError for hard failures.
        """
        ...

    @abstractmethod
    def extract_metadata(
        self,
        file_path: str,
        mime_type: str,
    ) -> dict[str, Any]:
        """
        Extract all available metadata from the file.

        Returns a dict of metadata key-values.
        """
        ...

    def can_handle(self, mime_type: str) -> bool:
        """Check if this handler supports the given MIME type."""
        return mime_type in self.supported_mime_types
