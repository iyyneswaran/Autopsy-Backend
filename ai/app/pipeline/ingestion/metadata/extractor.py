"""
Atopsy — Metadata Extraction Orchestrator.

Routes files to the appropriate metadata extractor
based on their category. Returns unified metadata dicts.
"""

from __future__ import annotations

from typing import Any

from app.core.logger import logger
from app.pipeline.ingestion.handlers.document import DocumentHandler
from app.pipeline.ingestion.handlers.image import ImageHandler
from app.pipeline.ingestion.handlers.video import VideoHandler
from app.pipeline.ingestion.handlers.structured import StructuredHandler
from app.pipeline.ingestion.handlers.base import FileHandler


# Handler registry — singleton instances
_HANDLERS: list[FileHandler] = [
    DocumentHandler(),
    ImageHandler(),
    VideoHandler(),
    StructuredHandler(),
]


def get_handler_for_mime(mime_type: str) -> FileHandler | None:
    """Return the appropriate handler for a given MIME type."""
    for handler in _HANDLERS:
        if handler.can_handle(mime_type):
            return handler
    return None


def extract_metadata(
    file_path: str,
    mime_type: str,
) -> dict[str, Any]:
    """
    Extract metadata from a file using the appropriate handler.

    Returns a metadata dict. If no handler is found, returns
    a minimal metadata dict with a warning.
    """
    handler = get_handler_for_mime(mime_type)

    if handler is None:
        logger.warning(
            f"No handler for MIME type: {mime_type}"
        )
        return {
            "meta_type": "unknown",
            "warning": f"No handler for {mime_type}",
        }

    try:
        return handler.extract_metadata(file_path, mime_type)
    except Exception as e:
        logger.error(
            f"Metadata extraction failed for {file_path}: {e}"
        )
        return {
            "meta_type": "error",
            "error": str(e),
        }


def validate_file(
    file_path: str,
    mime_type: str,
) -> list[str]:
    """
    Validate a file using the appropriate handler.

    Returns a list of warning strings. Raises on hard failures.
    """
    handler = get_handler_for_mime(mime_type)

    if handler is None:
        return [f"No validator for MIME type: {mime_type}"]

    return handler.validate(file_path, mime_type)
