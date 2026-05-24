"""
Atopsy — Centralized Exception Hierarchy.

All domain-specific exceptions inherit from AtopsyBaseError
for consistent error handling across the pipeline.
"""

from app.exceptions.pipeline import (
    AtopsyBaseError,
    PipelineError,
    IngestionError,
    NormalizationError,
    FileValidationError,
    ChecksumMismatchError,
    DuplicateEvidenceError,
    UnsupportedFileTypeError,
    FileSizeLimitError,
    MetadataExtractionError,
    StorageError,
    CorruptedDataError,
    AnomalyDetectedError,
    QualityThresholdError,
    ExtractionError,
    NLPExtractionError,
    TextAssemblyError,
    EntityStructuringError,
    EntityValidationError,
    ProvenanceError,
)

__all__ = [
    "AtopsyBaseError",
    "PipelineError",
    "IngestionError",
    "NormalizationError",
    "FileValidationError",
    "ChecksumMismatchError",
    "DuplicateEvidenceError",
    "UnsupportedFileTypeError",
    "FileSizeLimitError",
    "MetadataExtractionError",
    "StorageError",
    "CorruptedDataError",
    "AnomalyDetectedError",
    "QualityThresholdError",
    "ExtractionError",
    "NLPExtractionError",
    "TextAssemblyError",
    "EntityStructuringError",
    "EntityValidationError",
    "ProvenanceError",
]
