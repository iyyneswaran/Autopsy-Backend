"""
Atopsy — Data Acquisition Engine (Layer 1).

Orchestrates the complete evidence ingestion pipeline:
  Upload → Validate → Store → Fingerprint → Dedup → Metadata → Log

This is the primary entry point for all evidence ingestion,
whether single files, batch uploads, or structured JSON payloads.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from datetime import datetime, timezone
from typing import Any, BinaryIO

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logger import logger
from app.exceptions.pipeline import (
    DuplicateEvidenceError,
    FileValidationError,
    FileSizeLimitError,
    IngestionError,
    MetadataExtractionError,
    StorageError,
    UnsupportedFileTypeError,
)
from app.models.pipeline import (
    AcquisitionLog,
    EvidenceFile,
    FileCategory,
    FileChecksum,
    IngestionStatus,
    MetadataRecord,
    UploadSession,
)
from app.pipeline.ingestion.checksum import (
    ChecksumResult,
    check_duplicate,
    compute_checksums_from_file,
)
from app.pipeline.ingestion.handlers.base import (
    ALLOWED_MIME_TYPES,
    get_category_for_mime,
    resolve_mime_type,
)
from app.pipeline.ingestion.metadata.extractor import (
    extract_metadata,
    validate_file,
)
from app.storage.backend import StorageBackend, get_storage_backend


class IngestionEngine:
    """
    Enterprise-grade forensic data acquisition engine.

    Provides:
    - Single file ingestion
    - Batch upload sessions
    - Structured JSON ingestion
    - MIME validation & spoofing prevention
    - SHA-256 fingerprinting & deduplication
    - Automatic metadata extraction
    - Immutable audit logging
    - Provenance tracking
    """

    def __init__(
        self,
        db: Session,
        storage: StorageBackend | None = None,
        user_id: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        self.db = db
        self.storage = storage or get_storage_backend()
        self.user_id = user_id
        self.correlation_id = correlation_id or str(uuid.uuid4())

    # ─────────────────────────────────────────
    # Single File Ingestion
    # ─────────────────────────────────────────

    def ingest_file(
        self,
        file_stream: BinaryIO,
        filename: str,
        declared_mime: str | None = None,
        case_id: str | None = None,
        tags: list[str] | None = None,
        source_attribution: str | None = None,
    ) -> dict[str, Any]:
        """
        Ingest a single evidence file through the full pipeline.

        Returns a dict with evidence_file_id, status, metadata, etc.
        """
        start_time = time.monotonic()
        evidence_file_id = uuid.uuid4()

        self._log_event(
            "INGESTION_STARTED",
            evidence_file_id=str(evidence_file_id),
            detail=f"Starting ingestion of '{filename}'",
            context={"filename": filename, "declared_mime": declared_mime},
        )

        try:
            # ── Step 1: Resolve & Validate MIME type ──
            mime_type = resolve_mime_type(declared_mime, filename)
            if not mime_type or mime_type not in ALLOWED_MIME_TYPES:
                raise UnsupportedFileTypeError(declared_mime or "unknown")

            category_str = get_category_for_mime(mime_type)
            if not category_str:
                raise UnsupportedFileTypeError(mime_type)
            category = FileCategory(category_str)

            # ── Step 2: Save to temp for processing ──
            temp_dir = settings.TEMP_DIR
            os.makedirs(temp_dir, exist_ok=True)
            temp_path = os.path.join(
                temp_dir, f"{evidence_file_id}_{filename}"
            )

            try:
                with open(temp_path, "wb") as tmp:
                    while chunk := file_stream.read(settings.PIPELINE_CHUNK_SIZE):
                        tmp.write(chunk)
            except OSError as e:
                raise StorageError(f"Failed to write temp file: {e}")

            # ── Step 3: Size check ──
            file_size = os.path.getsize(temp_path)
            if file_size > settings.PIPELINE_MAX_FILE_SIZE:
                self._cleanup_temp(temp_path)
                raise FileSizeLimitError(file_size, settings.PIPELINE_MAX_FILE_SIZE)

            if file_size == 0:
                self._cleanup_temp(temp_path)
                raise FileValidationError("File is empty (0 bytes)")

            # ── Step 4: Compute checksums ──
            checksums: ChecksumResult = compute_checksums_from_file(temp_path)

            # ── Step 5: Duplicate detection ──
            dup = check_duplicate(checksums.sha256, self.db)
            if dup:
                self._cleanup_temp(temp_path)
                self._log_event(
                    "DUPLICATE_DETECTED",
                    evidence_file_id=str(evidence_file_id),
                    detail=f"Duplicate of {dup['evidence_file_id']}",
                    context=dup,
                )
                raise DuplicateEvidenceError(
                    checksums.sha256, dup["evidence_file_id"]
                )

            # ── Step 6: Validate file contents ──
            validation_warnings = validate_file(temp_path, mime_type)
            if validation_warnings:
                logger.warning(
                    f"Validation warnings for {filename}: {validation_warnings}"
                )

            # ── Step 7: Persist to storage backend ──
            with open(temp_path, "rb") as f:
                storage_result = self.storage.save(
                    f, category.value.lower(), filename
                )

            # ── Step 8: Extract metadata ──
            metadata_dict = extract_metadata(temp_path, mime_type)

            # ── Step 9: Create database records ──
            evidence_file = EvidenceFile(
                id=evidence_file_id,
                original_filename=filename,
                mime_type=mime_type,
                category=category,
                storage_key=storage_result["storage_key"],
                storage_path=storage_result["storage_path"],
                file_size=file_size,
                sha256_hash=checksums.sha256,
                md5_hash=checksums.md5,
                status=IngestionStatus.COMPLETED,
                case_id=uuid.UUID(case_id) if case_id else None,
                uploaded_by=(
                    uuid.UUID(self.user_id) if self.user_id else None
                ),
                tags=tags or [],
                source_attribution=source_attribution,
                provenance={
                    "ingested_at": datetime.now(timezone.utc).isoformat(),
                    "correlation_id": self.correlation_id,
                    "user_id": self.user_id,
                    "validation_warnings": validation_warnings,
                },
            )
            self.db.add(evidence_file)

            # Checksum record
            checksum_record = FileChecksum(
                evidence_file_id=evidence_file_id,
                sha256=checksums.sha256,
                md5=checksums.md5,
                file_size=file_size,
            )
            self.db.add(checksum_record)

            # Metadata record
            meta_record = MetadataRecord(
                evidence_file_id=evidence_file_id,
                meta_type=metadata_dict.get("meta_type", "unknown"),
                extracted_data=metadata_dict,
                warnings=validation_warnings,
            )
            self.db.add(meta_record)

            self.db.commit()

            # ── Step 10: Cleanup temp ──
            self._cleanup_temp(temp_path)

            elapsed = round(time.monotonic() - start_time, 3)

            self._log_event(
                "INGESTION_COMPLETED",
                evidence_file_id=str(evidence_file_id),
                detail=f"Ingestion of '{filename}' completed in {elapsed}s",
                context={
                    "elapsed_seconds": elapsed,
                    "file_size": file_size,
                    "sha256": checksums.sha256,
                    "category": category.value,
                },
            )

            return {
                "evidence_file_id": str(evidence_file_id),
                "status": "COMPLETED",
                "original_filename": filename,
                "mime_type": mime_type,
                "category": category.value,
                "file_size": file_size,
                "sha256_hash": checksums.sha256,
                "storage_key": storage_result["storage_key"],
                "metadata": metadata_dict,
                "validation_warnings": validation_warnings,
                "elapsed_seconds": elapsed,
            }

        except (
            UnsupportedFileTypeError,
            FileSizeLimitError,
            DuplicateEvidenceError,
            FileValidationError,
        ):
            raise

        except Exception as e:
            self._log_event(
                "INGESTION_FAILED",
                evidence_file_id=str(evidence_file_id),
                detail=f"Ingestion failed: {str(e)}",
                context={"error": str(e)},
            )
            logger.error(f"Ingestion failed for '{filename}': {e}")
            raise IngestionError(
                f"Ingestion failed: {e}",
                context={"filename": filename},
            ) from e

    # ─────────────────────────────────────────
    # Batch Upload Session
    # ─────────────────────────────────────────

    def create_batch_session(
        self,
        total_files: int,
        case_id: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a batch upload session."""
        session = UploadSession(
            user_id=(
                uuid.UUID(self.user_id) if self.user_id else None
            ),
            case_id=uuid.UUID(case_id) if case_id else None,
            total_files=total_files,
            status=IngestionStatus.UPLOADING,
            session_metadata={"tags": tags or []},
        )
        self.db.add(session)
        self.db.commit()

        self._log_event(
            "BATCH_SESSION_CREATED",
            detail=f"Batch session created for {total_files} files",
            context={
                "session_id": str(session.id),
                "total_files": total_files,
            },
        )

        return {
            "session_id": str(session.id),
            "total_files": total_files,
            "status": "UPLOADING",
        }

    def add_to_batch(
        self,
        session_id: str,
        file_stream: BinaryIO,
        filename: str,
        declared_mime: str | None = None,
    ) -> dict[str, Any]:
        """Add a file to an existing batch session."""
        session = (
            self.db.query(UploadSession)
            .filter(UploadSession.id == uuid.UUID(session_id))
            .first()
        )
        if not session:
            raise IngestionError(f"Session {session_id} not found")

        try:
            result = self.ingest_file(
                file_stream=file_stream,
                filename=filename,
                declared_mime=declared_mime,
                case_id=str(session.case_id) if session.case_id else None,
                tags=session.session_metadata.get("tags", []),
            )
            session.completed_files += 1
        except Exception as e:
            session.failed_files += 1
            result = {
                "status": "FAILED",
                "error": str(e),
                "filename": filename,
            }

        # Check if batch is complete
        if (session.completed_files + session.failed_files) >= session.total_files:
            session.status = IngestionStatus.COMPLETED
            session.completed_at = datetime.now(timezone.utc)

        self.db.commit()
        return result

    # ─────────────────────────────────────────
    # Structured JSON Ingestion
    # ─────────────────────────────────────────

    def ingest_structured(
        self,
        data: dict[str, Any],
        evidence_type: str,
        case_id: str | None = None,
        tags: list[str] | None = None,
        source_attribution: str | None = None,
    ) -> dict[str, Any]:
        """Ingest structured JSON evidence via API payload."""
        evidence_file_id = uuid.uuid4()

        # Serialize to temp file for consistent processing
        temp_dir = settings.TEMP_DIR
        os.makedirs(temp_dir, exist_ok=True)
        filename = f"{evidence_type}_{evidence_file_id}.json"
        temp_path = os.path.join(temp_dir, filename)

        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, default=str, indent=2)

        try:
            with open(temp_path, "rb") as f:
                return self.ingest_file(
                    file_stream=f,
                    filename=filename,
                    declared_mime="application/json",
                    case_id=case_id,
                    tags=tags,
                    source_attribution=source_attribution,
                )
        finally:
            self._cleanup_temp(temp_path)

    # ─────────────────────────────────────────
    # Audit Logging
    # ─────────────────────────────────────────

    def _log_event(
        self,
        action: str,
        evidence_file_id: str | None = None,
        detail: str | None = None,
        context: dict | None = None,
    ) -> None:
        """Write an immutable acquisition log entry."""
        try:
            log = AcquisitionLog(
                evidence_file_id=(
                    uuid.UUID(evidence_file_id) if evidence_file_id else None
                ),
                user_id=(
                    uuid.UUID(self.user_id) if self.user_id else None
                ),
                action=action,
                detail=detail,
                context=context or {},
                correlation_id=self.correlation_id,
            )
            self.db.add(log)
            self.db.flush()
        except Exception as e:
            logger.error(f"Failed to write audit log: {e}")

    # ─────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────

    @staticmethod
    def _cleanup_temp(path: str) -> None:
        """Safely remove a temporary file."""
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError as e:
            logger.warning(f"Failed to cleanup temp file {path}: {e}")
