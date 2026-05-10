"""
Atopsy — Pipeline Repository Layer.

Data access layer for all pipeline models.
Follows the repository pattern for clean separation
between business logic and data persistence.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.pipeline import (
    AcquisitionLog,
    EvidenceFile,
    FileChecksum,
    IngestionStatus,
    MetadataRecord,
    NormalizationRecord,
    NormalizationStatus,
    UploadSession,
)


class PipelineRepository:
    """Repository for all pipeline data access operations."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ── EvidenceFile ─────────────────────────

    def get_evidence_file(
        self, file_id: str
    ) -> EvidenceFile | None:
        return (
            self.db.query(EvidenceFile)
            .filter(
                EvidenceFile.id == uuid.UUID(file_id),
                EvidenceFile.is_deleted == False,
            )
            .first()
        )

    def list_evidence_files(
        self,
        case_id: str | None = None,
        category: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[EvidenceFile]:
        query = self.db.query(EvidenceFile).filter(
            EvidenceFile.is_deleted == False
        )

        if case_id:
            query = query.filter(
                EvidenceFile.case_id == uuid.UUID(case_id)
            )
        if category:
            query = query.filter(EvidenceFile.category == category)
        if status:
            query = query.filter(EvidenceFile.status == status)

        return (
            query.order_by(EvidenceFile.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    def count_evidence_files(
        self,
        status: str | None = None,
    ) -> int:
        query = self.db.query(EvidenceFile).filter(
            EvidenceFile.is_deleted == False
        )
        if status:
            query = query.filter(EvidenceFile.status == status)
        return query.count()

    def soft_delete_evidence(self, file_id: str) -> bool:
        record = self.get_evidence_file(file_id)
        if record:
            record.is_deleted = True
            record.deleted_at = datetime.now(timezone.utc)
            self.db.commit()
            return True
        return False

    # ── UploadSession ────────────────────────

    def get_upload_session(
        self, session_id: str
    ) -> UploadSession | None:
        return (
            self.db.query(UploadSession)
            .filter(UploadSession.id == uuid.UUID(session_id))
            .first()
        )

    def list_upload_sessions(
        self,
        user_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[UploadSession]:
        query = self.db.query(UploadSession)
        if user_id:
            query = query.filter(
                UploadSession.user_id == uuid.UUID(user_id)
            )
        return (
            query.order_by(UploadSession.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    # ── AcquisitionLog ───────────────────────

    def list_acquisition_logs(
        self,
        evidence_file_id: str | None = None,
        action: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AcquisitionLog]:
        query = self.db.query(AcquisitionLog)

        if evidence_file_id:
            query = query.filter(
                AcquisitionLog.evidence_file_id
                == uuid.UUID(evidence_file_id)
            )
        if action:
            query = query.filter(AcquisitionLog.action == action)

        return (
            query.order_by(AcquisitionLog.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    # ── MetadataRecord ───────────────────────

    def get_metadata_for_evidence(
        self, evidence_file_id: str
    ) -> list[MetadataRecord]:
        return (
            self.db.query(MetadataRecord)
            .filter(
                MetadataRecord.evidence_file_id
                == uuid.UUID(evidence_file_id)
            )
            .all()
        )

    # ── NormalizationRecord ──────────────────

    def get_normalization_for_evidence(
        self, evidence_file_id: str
    ) -> NormalizationRecord | None:
        return (
            self.db.query(NormalizationRecord)
            .filter(
                NormalizationRecord.evidence_file_id
                == uuid.UUID(evidence_file_id)
            )
            .order_by(NormalizationRecord.created_at.desc())
            .first()
        )

    def list_pending_normalizations(
        self, limit: int = 50
    ) -> list[EvidenceFile]:
        """Find evidence files that completed ingestion but lack normalization."""
        normalized_ids = (
            self.db.query(NormalizationRecord.evidence_file_id)
            .filter(
                NormalizationRecord.status.in_([
                    NormalizationStatus.COMPLETED,
                    NormalizationStatus.IN_PROGRESS,
                ])
            )
            .subquery()
            .select()
        )

        return (
            self.db.query(EvidenceFile)
            .filter(
                EvidenceFile.status == IngestionStatus.COMPLETED,
                EvidenceFile.is_deleted == False,
                ~EvidenceFile.id.in_(normalized_ids),
            )
            .order_by(EvidenceFile.created_at.asc())
            .limit(limit)
            .all()
        )

    def count_pending_normalizations(self) -> int:
        normalized_ids = (
            self.db.query(NormalizationRecord.evidence_file_id)
            .filter(
                NormalizationRecord.status.in_([
                    NormalizationStatus.COMPLETED,
                    NormalizationStatus.IN_PROGRESS,
                ])
            )
            .subquery()
            .select()
        )
        return (
            self.db.query(EvidenceFile)
            .filter(
                EvidenceFile.status == IngestionStatus.COMPLETED,
                EvidenceFile.is_deleted == False,
                ~EvidenceFile.id.in_(normalized_ids),
            )
            .count()
        )

    # ── FileChecksum ─────────────────────────

    def find_by_checksum(self, sha256: str) -> FileChecksum | None:
        return (
            self.db.query(FileChecksum)
            .filter(FileChecksum.sha256 == sha256)
            .first()
        )
