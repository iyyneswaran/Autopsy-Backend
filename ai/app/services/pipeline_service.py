"""
Atopsy — Pipeline Service Layer.

Business logic orchestrating ingestion → normalization.
Sits between API endpoints and the pipeline engines.
"""

from __future__ import annotations

import time
from typing import Any, BinaryIO

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logger import logger
from app.pipeline.ingestion.engine import IngestionEngine
from app.pipeline.normalization.engine import NormalizationEngine
from app.repositories.pipeline_repository import PipelineRepository
from app.storage.backend import get_storage_backend


class PipelineService:
    """
    Service layer for the forensic intelligence pipeline.

    Coordinates ingestion and normalization engines,
    provides high-level operations for the API layer.
    """

    def __init__(
        self,
        db: Session,
        user_id: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        self.db = db
        self.user_id = user_id
        self.correlation_id = correlation_id
        self.repo = PipelineRepository(db)
        self.storage = get_storage_backend()

    # ─────────────────────────────────────────
    # Ingestion Operations
    # ─────────────────────────────────────────

    def ingest_file(
        self,
        file_stream: BinaryIO,
        filename: str,
        content_type: str | None = None,
        case_id: str | None = None,
        tags: list[str] | None = None,
        source_attribution: str | None = None,
        auto_normalize: bool = True,
    ) -> dict[str, Any]:
        """
        Ingest a single file and optionally auto-normalize.

        Returns combined ingestion + normalization results.
        """
        engine = IngestionEngine(
            db=self.db,
            storage=self.storage,
            user_id=self.user_id,
            correlation_id=self.correlation_id,
        )

        # Ingest
        result = engine.ingest_file(
            file_stream=file_stream,
            filename=filename,
            declared_mime=content_type,
            case_id=case_id,
            tags=tags,
            source_attribution=source_attribution,
        )

        # Auto-normalize if ingestion succeeded
        if auto_normalize and result.get("status") == "COMPLETED":
            try:
                norm_engine = NormalizationEngine(self.db)
                norm_result = norm_engine.normalize(
                    result["evidence_file_id"]
                )
                result["normalization"] = norm_result
            except Exception as e:
                logger.warning(
                    f"Auto-normalization failed: {e}"
                )
                result["normalization"] = {
                    "status": "FAILED",
                    "error": str(e),
                }

        return result

    def ingest_batch(
        self,
        files: list[tuple[BinaryIO, str, str | None]],
        case_id: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Ingest a batch of files.

        Args:
            files: List of (stream, filename, content_type) tuples.

        Returns:
            Batch results summary.
        """
        engine = IngestionEngine(
            db=self.db,
            storage=self.storage,
            user_id=self.user_id,
            correlation_id=self.correlation_id,
        )

        session_result = engine.create_batch_session(
            total_files=len(files),
            case_id=case_id,
            tags=tags,
        )

        results: list[dict[str, Any]] = []
        for stream, filename, content_type in files:
            file_result = engine.add_to_batch(
                session_id=session_result["session_id"],
                file_stream=stream,
                filename=filename,
                declared_mime=content_type,
            )
            results.append(file_result)

        completed = sum(
            1 for r in results if r.get("status") == "COMPLETED"
        )
        failed = sum(
            1 for r in results if r.get("status") == "FAILED"
        )

        return {
            "session_id": session_result["session_id"],
            "total_files": len(files),
            "completed": completed,
            "failed": failed,
            "results": results,
        }

    def ingest_structured(
        self,
        data: dict[str, Any],
        evidence_type: str,
        case_id: str | None = None,
        tags: list[str] | None = None,
        source_attribution: str | None = None,
    ) -> dict[str, Any]:
        """Ingest structured JSON evidence."""
        engine = IngestionEngine(
            db=self.db,
            storage=self.storage,
            user_id=self.user_id,
            correlation_id=self.correlation_id,
        )

        result = engine.ingest_structured(
            data=data,
            evidence_type=evidence_type,
            case_id=case_id,
            tags=tags,
            source_attribution=source_attribution,
        )

        # Auto-normalize
        if result.get("status") == "COMPLETED":
            try:
                norm_engine = NormalizationEngine(self.db)
                norm_result = norm_engine.normalize(
                    result["evidence_file_id"]
                )
                result["normalization"] = norm_result
            except Exception as e:
                result["normalization"] = {
                    "status": "FAILED",
                    "error": str(e),
                }

        return result

    # ─────────────────────────────────────────
    # Normalization Operations
    # ─────────────────────────────────────────

    def normalize_evidence(
        self, evidence_file_id: str
    ) -> dict[str, Any]:
        """Trigger normalization for a specific evidence file."""
        engine = NormalizationEngine(self.db)
        return engine.normalize(evidence_file_id)

    def normalize_pending(self) -> dict[str, Any]:
        """Normalize all pending evidence files."""
        pending = self.repo.list_pending_normalizations(limit=50)
        engine = NormalizationEngine(self.db)

        results: list[dict[str, Any]] = []
        for evidence in pending:
            try:
                result = engine.normalize(str(evidence.id))
                results.append(result)
            except Exception as e:
                results.append({
                    "evidence_file_id": str(evidence.id),
                    "status": "FAILED",
                    "error": str(e),
                })

        return {
            "total_processed": len(results),
            "completed": sum(
                1 for r in results
                if r.get("status") in ("COMPLETED", "PARTIAL")
            ),
            "failed": sum(
                1 for r in results if r.get("status") == "FAILED"
            ),
            "results": results,
        }

    # ─────────────────────────────────────────
    # Query Operations
    # ─────────────────────────────────────────

    def get_evidence_detail(
        self, evidence_file_id: str
    ) -> dict[str, Any] | None:
        """Get full detail for an evidence file including metadata and normalization."""
        evidence = self.repo.get_evidence_file(evidence_file_id)
        if not evidence:
            return None

        metadata = self.repo.get_metadata_for_evidence(
            evidence_file_id
        )
        normalization = self.repo.get_normalization_for_evidence(
            evidence_file_id
        )

        result: dict[str, Any] = {
            "id": str(evidence.id),
            "original_filename": evidence.original_filename,
            "mime_type": evidence.mime_type,
            "category": evidence.category.value if hasattr(evidence.category, 'value') else str(evidence.category),
            "file_size": evidence.file_size,
            "sha256_hash": evidence.sha256_hash,
            "status": evidence.status.value if hasattr(evidence.status, 'value') else str(evidence.status),
            "tags": evidence.tags,
            "source_attribution": evidence.source_attribution,
            "case_id": str(evidence.case_id) if evidence.case_id else None,
            "created_at": evidence.created_at.isoformat() if evidence.created_at else None,
        }

        if metadata:
            result["metadata"] = [
                {
                    "meta_type": m.meta_type,
                    "data": m.extracted_data,
                    "confidence": m.confidence,
                    "warnings": m.warnings,
                }
                for m in metadata
            ]

        if normalization:
            result["normalization"] = {
                "id": str(normalization.id),
                "status": normalization.status.value if hasattr(normalization.status, 'value') else str(normalization.status),
                "quality_score": normalization.quality_score,
                "completeness_score": normalization.completeness_score,
                "confidence_score": normalization.confidence_score,
                "anomaly_count": normalization.anomaly_count,
                "canonical_output": normalization.canonical_output,
                "quality_report": normalization.quality_report,
            }

        return result

    def list_evidence(
        self,
        case_id: str | None = None,
        category: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """List evidence files with pagination."""
        files = self.repo.list_evidence_files(
            case_id=case_id,
            category=category,
            status=status,
            limit=limit,
            offset=offset,
        )

        total = self.repo.count_evidence_files(status=status)

        return {
            "items": [
                {
                    "id": str(f.id),
                    "original_filename": f.original_filename,
                    "mime_type": f.mime_type,
                    "category": f.category.value if hasattr(f.category, 'value') else str(f.category),
                    "file_size": f.file_size,
                    "status": f.status.value if hasattr(f.status, 'value') else str(f.status),
                    "sha256_hash": f.sha256_hash,
                    "created_at": f.created_at.isoformat() if f.created_at else None,
                }
                for f in files
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def get_acquisition_logs(
        self,
        evidence_file_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Get acquisition audit logs."""
        logs = self.repo.list_acquisition_logs(
            evidence_file_id=evidence_file_id,
            limit=limit,
            offset=offset,
        )

        return [
            {
                "id": str(log.id),
                "evidence_file_id": str(log.evidence_file_id) if log.evidence_file_id else None,
                "action": log.action,
                "detail": log.detail,
                "context": log.context,
                "correlation_id": log.correlation_id,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ]

    def get_pipeline_health(self) -> dict[str, Any]:
        """Get pipeline health status."""
        try:
            pending_ingestions = self.repo.count_evidence_files(
                status="PENDING"
            )
            pending_normalizations = self.repo.count_pending_normalizations()
            status = "healthy"
        except Exception as e:
            logger.warning(f"Pipeline health check query failed: {e}")
            pending_ingestions = 0
            pending_normalizations = 0
            status = "degraded"

        return {
            "status": status,
            "storage_backend": settings.STORAGE_BACKEND,
            "pending_ingestions": pending_ingestions,
            "pending_normalizations": pending_normalizations,
        }

    def get_download_path(
        self, evidence_file_id: str
    ) -> str | None:
        """Get the storage path or signed URL for an evidence file."""
        evidence = self.repo.get_evidence_file(evidence_file_id)
        if not evidence:
            return None

        result = self.storage.retrieve(evidence.storage_key)
        return str(result)
