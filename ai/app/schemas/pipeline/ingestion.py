"""
Atopsy — Ingestion Pydantic v2 Schemas.

Request/response schemas for the data acquisition layer.
Strict validation with comprehensive field constraints.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


# ─────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────


class FileCategoryEnum(str, Enum):
    DOCUMENT = "DOCUMENT"
    IMAGE = "IMAGE"
    VIDEO = "VIDEO"
    STRUCTURED = "STRUCTURED"


class IngestionStatusEnum(str, Enum):
    PENDING = "PENDING"
    UPLOADING = "UPLOADING"
    VALIDATING = "VALIDATING"
    EXTRACTING_METADATA = "EXTRACTING_METADATA"
    NORMALIZING = "NORMALIZING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    DUPLICATE = "DUPLICATE"


# ─────────────────────────────────────────────
# Upload Requests
# ─────────────────────────────────────────────


class UploadRequest(BaseModel):
    """Metadata sent alongside a file upload."""

    model_config = ConfigDict(strict=True)

    case_id: UUID | None = None
    tags: list[str] = Field(default_factory=list, max_length=50)
    source_attribution: str | None = Field(
        None, max_length=512, description="Origin of the evidence"
    )
    description: str | None = Field(None, max_length=2048)


class BatchUploadRequest(BaseModel):
    """Request to initiate a batch upload session."""

    model_config = ConfigDict(strict=True)

    case_id: UUID | None = None
    total_files: int = Field(..., ge=1, le=100)
    tags: list[str] = Field(default_factory=list)
    source_attribution: str | None = None


class ResumableUploadInit(BaseModel):
    """Initialize a resumable (chunked) upload."""

    model_config = ConfigDict(strict=True)

    filename: str = Field(..., max_length=512)
    file_size: int = Field(..., ge=1)
    mime_type: str = Field(..., max_length=255)
    case_id: UUID | None = None
    chunk_size: int = Field(default=5 * 1024 * 1024, ge=1024)


class StructuredEvidencePayload(BaseModel):
    """JSON evidence ingested via API (not file upload)."""

    model_config = ConfigDict(strict=True)

    case_id: UUID | None = None
    evidence_type: str = Field(
        ..., max_length=100, description="e.g. forensic_metadata, gps_feed"
    )
    data: dict[str, Any] = Field(
        ..., description="Structured forensic data payload"
    )
    source_attribution: str | None = None
    tags: list[str] = Field(default_factory=list)


# ─────────────────────────────────────────────
# Responses
# ─────────────────────────────────────────────


class EvidenceFileResponse(BaseModel):
    """Response after a successful file ingestion."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    original_filename: str
    mime_type: str
    category: str
    storage_key: str
    file_size: int
    sha256_hash: str
    status: str
    version: int
    tags: list[str]
    source_attribution: str | None
    case_id: UUID | None
    created_at: datetime


class UploadSessionResponse(BaseModel):
    """Response for a batch/resumable upload session."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: str
    total_files: int
    completed_files: int
    failed_files: int
    is_resumable: bool
    created_at: datetime
    completed_at: datetime | None


class UploadStatusResponse(BaseModel):
    """Status check for an individual upload."""

    evidence_file_id: UUID
    status: str
    progress_pct: float = 0.0
    error_message: str | None = None


class AcquisitionLogResponse(BaseModel):
    """Single acquisition audit log entry."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    evidence_file_id: UUID | None
    action: str
    detail: str | None
    context: dict[str, Any]
    correlation_id: str | None
    created_at: datetime


class MetadataResponse(BaseModel):
    """Extracted metadata for an evidence file."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    evidence_file_id: UUID
    meta_type: str
    extracted_data: dict[str, Any]
    confidence: float
    warnings: list[str]
    created_at: datetime


class PipelineHealthResponse(BaseModel):
    """Pipeline subsystem health status."""

    status: str = "healthy"
    storage_backend: str
    pending_ingestions: int = 0
    pending_normalizations: int = 0
    uptime_seconds: float = 0.0
