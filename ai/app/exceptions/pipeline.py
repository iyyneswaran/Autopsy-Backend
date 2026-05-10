"""
Atopsy — Pipeline Exception Hierarchy.

Typed, structured exceptions for the forensic intelligence pipeline.
Each exception carries a machine-readable error code, HTTP status mapping,
and optional context dict for structured logging.
"""

from __future__ import annotations

from typing import Any


class AtopsyBaseError(Exception):
    """Root exception for all Atopsy domain errors."""

    status_code: int = 500
    error_code: str = "ATOPSY_INTERNAL_ERROR"

    def __init__(
        self,
        message: str = "An internal error occurred",
        *,
        context: dict[str, Any] | None = None,
    ) -> None:
        self.message = message
        self.context = context or {}
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_code": self.error_code,
            "message": self.message,
            "context": self.context,
        }


# ─────────────────────────────────────────────
# Pipeline-level errors
# ─────────────────────────────────────────────


class PipelineError(AtopsyBaseError):
    """Generic pipeline processing error."""

    status_code = 500
    error_code = "PIPELINE_ERROR"


class IngestionError(PipelineError):
    """Error during the data acquisition phase."""

    error_code = "INGESTION_ERROR"


class NormalizationError(PipelineError):
    """Error during the data normalization phase."""

    error_code = "NORMALIZATION_ERROR"


# ─────────────────────────────────────────────
# File validation errors
# ─────────────────────────────────────────────


class FileValidationError(IngestionError):
    """Base class for file validation failures."""

    status_code = 400
    error_code = "FILE_VALIDATION_ERROR"


class UnsupportedFileTypeError(FileValidationError):
    """Uploaded file MIME type is not in the allow-list."""

    error_code = "UNSUPPORTED_FILE_TYPE"

    def __init__(self, mime_type: str, **kwargs: Any) -> None:
        super().__init__(
            f"File type '{mime_type}' is not supported",
            context={"mime_type": mime_type},
            **kwargs,
        )


class FileSizeLimitError(FileValidationError):
    """Uploaded file exceeds the maximum allowed size."""

    error_code = "FILE_SIZE_LIMIT_EXCEEDED"

    def __init__(
        self, file_size: int, max_size: int, **kwargs: Any
    ) -> None:
        super().__init__(
            f"File size {file_size} bytes exceeds limit of {max_size} bytes",
            context={
                "file_size": file_size,
                "max_size": max_size,
            },
            **kwargs,
        )


class ChecksumMismatchError(FileValidationError):
    """File checksum does not match the expected value."""

    error_code = "CHECKSUM_MISMATCH"

    def __init__(
        self,
        expected: str,
        actual: str,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            "File checksum verification failed",
            context={
                "expected": expected,
                "actual": actual,
            },
            **kwargs,
        )


class DuplicateEvidenceError(FileValidationError):
    """Evidence file with the same fingerprint already exists."""

    status_code = 409
    error_code = "DUPLICATE_EVIDENCE"

    def __init__(
        self,
        sha256: str,
        existing_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            "Duplicate evidence detected",
            context={
                "sha256": sha256,
                "existing_evidence_id": existing_id,
            },
            **kwargs,
        )


# ─────────────────────────────────────────────
# Processing errors
# ─────────────────────────────────────────────


class MetadataExtractionError(IngestionError):
    """Failed to extract metadata from an evidence file."""

    error_code = "METADATA_EXTRACTION_ERROR"


class StorageError(IngestionError):
    """Failed to persist a file to the storage backend."""

    error_code = "STORAGE_ERROR"


class CorruptedDataError(NormalizationError):
    """Evidence data is corrupt or malformed beyond recovery."""

    error_code = "CORRUPTED_DATA"


class AnomalyDetectedError(NormalizationError):
    """
    Pre-check detected an anomaly in the evidence data
    (impossible timestamps, invalid GPS, etc.).
    """

    status_code = 422
    error_code = "ANOMALY_DETECTED"


class QualityThresholdError(NormalizationError):
    """Normalized data does not meet the minimum quality threshold."""

    status_code = 422
    error_code = "QUALITY_THRESHOLD_NOT_MET"
