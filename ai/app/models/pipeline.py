"""
Atopsy — Pipeline SQLAlchemy Models.

Models for the forensic data acquisition and normalization layers.
All models use PostgreSQL-native UUIDs, timestamps, soft-delete,
and comprehensive indexing for query performance.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    String,
    Text,
    Integer,
    BigInteger,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy.orm import relationship

from app.core.database import Base


# ─────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────

import enum


class FileCategory(str, enum.Enum):
    DOCUMENT = "DOCUMENT"
    IMAGE = "IMAGE"
    VIDEO = "VIDEO"
    STRUCTURED = "STRUCTURED"


class IngestionStatus(str, enum.Enum):
    PENDING = "PENDING"
    UPLOADING = "UPLOADING"
    VALIDATING = "VALIDATING"
    EXTRACTING_METADATA = "EXTRACTING_METADATA"
    NORMALIZING = "NORMALIZING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    DUPLICATE = "DUPLICATE"


class NormalizationStatus(str, enum.Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ─────────────────────────────────────────────
# EvidenceFile — Core ingested file record
# ─────────────────────────────────────────────


class EvidenceFile(Base):
    """
    Represents a single ingested forensic evidence file.
    Immutable once created; new versions create new rows.
    """

    __tablename__ = "evidence_files"
    __table_args__ = (
        Index("ix_evidence_files_sha256", "sha256_hash"),
        Index("ix_evidence_files_category", "category"),
        Index("ix_evidence_files_status", "status"),
        Index("ix_evidence_files_case", "case_id"),
        Index("ix_evidence_files_created", "created_at"),
        {"extend_existing": True},
    )

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Source tracking
    original_filename = Column(String(512), nullable=False)
    mime_type = Column(String(255), nullable=False)
    category = Column(
        SAEnum(FileCategory, name="file_category_enum", create_type=False),
        nullable=False,
    )

    # Storage
    storage_key = Column(String(1024), nullable=False, unique=True)
    storage_path = Column(String(2048), nullable=False)
    file_size = Column(BigInteger, nullable=False, default=0)

    # Integrity
    sha256_hash = Column(String(64), nullable=False)
    md5_hash = Column(String(32), nullable=True)

    # Versioning
    version = Column(Integer, default=1, nullable=False)
    parent_file_id = Column(UUID(as_uuid=True), nullable=True)

    # Processing
    status = Column(
        SAEnum(IngestionStatus, name="ingestion_status_enum", create_type=False),
        default=IngestionStatus.PENDING,
        nullable=False,
    )
    error_message = Column(Text, nullable=True)

    # Relations
    case_id = Column(UUID(as_uuid=True), nullable=True)
    uploaded_by = Column(UUID(as_uuid=True), nullable=True)
    upload_session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("upload_sessions.id"),
        nullable=True,
    )

    # Tags & provenance
    tags = Column(JSON, default=list)
    source_attribution = Column(String(512), nullable=True)
    provenance = Column(JSON, default=dict)

    # Soft delete
    is_deleted = Column(Boolean, default=False, nullable=False)
    deleted_at = Column(DateTime, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=_utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=_utcnow, onupdate=_utcnow, nullable=False
    )

    # Relationships
    metadata_records = relationship(
        "MetadataRecord", back_populates="evidence_file", lazy="selectin"
    )
    normalization_records = relationship(
        "NormalizationRecord", back_populates="evidence_file", lazy="selectin"
    )


# ─────────────────────────────────────────────
# UploadSession — Batch / resumable upload tracking
# ─────────────────────────────────────────────


class UploadSession(Base):
    """Tracks a batch or resumable upload session."""

    __tablename__ = "upload_sessions"
    __table_args__ = (
        Index("ix_upload_sessions_user", "user_id"),
        Index("ix_upload_sessions_status", "status"),
        {"extend_existing": True},
    )

    id = Column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    user_id = Column(UUID(as_uuid=True), nullable=True)
    case_id = Column(UUID(as_uuid=True), nullable=True)

    # Session state
    status = Column(
        SAEnum(IngestionStatus, name="ingestion_status_enum", create_type=False),
        default=IngestionStatus.PENDING,
    )
    total_files = Column(Integer, default=0)
    completed_files = Column(Integer, default=0)
    failed_files = Column(Integer, default=0)

    # Resumable upload
    is_resumable = Column(Boolean, default=False)
    chunk_size = Column(Integer, nullable=True)
    uploaded_chunks = Column(JSON, default=list)

    # Session metadata (cannot use 'metadata' — reserved by SQLAlchemy)
    session_metadata = Column("session_metadata", JSON, default=dict)

    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)
    completed_at = Column(DateTime, nullable=True)


# ─────────────────────────────────────────────
# AcquisitionLog — Immutable audit log
# ─────────────────────────────────────────────


class AcquisitionLog(Base):
    """
    Immutable audit trail for every ingestion event.
    Forensic-grade: no updates or deletes allowed.
    """

    __tablename__ = "acquisition_logs"
    __table_args__ = (
        Index("ix_acq_log_evidence", "evidence_file_id"),
        Index("ix_acq_log_action", "action"),
        Index("ix_acq_log_created", "created_at"),
        {"extend_existing": True},
    )

    id = Column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    evidence_file_id = Column(UUID(as_uuid=True), nullable=True)
    upload_session_id = Column(UUID(as_uuid=True), nullable=True)
    user_id = Column(UUID(as_uuid=True), nullable=True)

    action = Column(String(100), nullable=False)
    detail = Column(Text, nullable=True)
    context = Column(JSON, default=dict)

    # Correlation
    correlation_id = Column(String(64), nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(512), nullable=True)

    created_at = Column(DateTime, default=_utcnow, nullable=False)


# ─────────────────────────────────────────────
# FileChecksum — Separate checksum storage for dedup
# ─────────────────────────────────────────────


class FileChecksum(Base):
    """
    Stores file checksums for fast duplicate detection.
    Unique constraint on sha256 enables O(1) dedup lookups.
    """

    __tablename__ = "file_checksums"
    __table_args__ = (
        Index("ix_checksum_sha256", "sha256", unique=True),
        {"extend_existing": True},
    )

    id = Column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    evidence_file_id = Column(
        UUID(as_uuid=True),
        ForeignKey("evidence_files.id"),
        nullable=False,
    )
    sha256 = Column(String(64), nullable=False, unique=True)
    md5 = Column(String(32), nullable=True)
    file_size = Column(BigInteger, nullable=False)

    created_at = Column(DateTime, default=_utcnow)


# ─────────────────────────────────────────────
# MetadataRecord — Extracted metadata per file
# ─────────────────────────────────────────────


class MetadataRecord(Base):
    """
    Stores extracted metadata (EXIF, document props, video info)
    as structured JSON keyed by extraction type.
    """

    __tablename__ = "metadata_records"
    __table_args__ = (
        Index("ix_meta_evidence", "evidence_file_id"),
        Index("ix_meta_type", "meta_type"),
        {"extend_existing": True},
    )

    id = Column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    evidence_file_id = Column(
        UUID(as_uuid=True),
        ForeignKey("evidence_files.id"),
        nullable=False,
    )

    meta_type = Column(
        String(50), nullable=False
    )  # "exif", "document", "video", "custom"

    extracted_data = Column(JSON, nullable=False, default=dict)
    extraction_version = Column(String(20), default="1.0.0")

    # Quality
    confidence = Column(Float, default=1.0)
    warnings = Column(JSON, default=list)

    created_at = Column(DateTime, default=_utcnow)

    evidence_file = relationship(
        "EvidenceFile", back_populates="metadata_records"
    )


# ─────────────────────────────────────────────
# NormalizationRecord — Normalized output per file
# ─────────────────────────────────────────────


class NormalizationRecord(Base):
    """
    Stores the normalized canonical output for each evidence file.
    Versioned and immutable — new normalizations create new rows.
    """

    __tablename__ = "normalization_records"
    __table_args__ = (
        Index("ix_norm_evidence", "evidence_file_id"),
        Index("ix_norm_status", "status"),
        {"extend_existing": True},
    )

    id = Column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    evidence_file_id = Column(
        UUID(as_uuid=True),
        ForeignKey("evidence_files.id"),
        nullable=False,
    )

    # Output
    status = Column(
        SAEnum(
            NormalizationStatus,
            name="normalization_status_enum",
            create_type=False,
        ),
        default=NormalizationStatus.PENDING,
    )
    canonical_output = Column(JSON, nullable=True)
    schema_version = Column(String(20), default="1.0.0")
    normalization_version = Column(Integer, default=1)

    # Quality metrics
    quality_score = Column(Float, default=0.0)
    completeness_score = Column(Float, default=0.0)
    confidence_score = Column(Float, default=0.0)
    quality_report = Column(JSON, default=dict)

    # Anomalies
    anomalies_detected = Column(JSON, default=list)
    anomaly_count = Column(Integer, default=0)

    # Stages completed
    stages_completed = Column(JSON, default=list)
    stages_failed = Column(JSON, default=list)

    # Error
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime, default=_utcnow)
    completed_at = Column(DateTime, nullable=True)

    evidence_file = relationship(
        "EvidenceFile", back_populates="normalization_records"
    )
