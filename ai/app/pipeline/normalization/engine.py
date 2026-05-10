"""
Atopsy — Data Normalization Engine (Layer 2).

Orchestrates the complete normalization pipeline:
  Raw Metadata → Clean → Transform → Enrich → Structure → Quality → Persist

Modular stage-based architecture with per-stage reporting.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logger import logger
from app.exceptions.pipeline import NormalizationError
from app.models.pipeline import (
    EvidenceFile,
    MetadataRecord,
    NormalizationRecord,
    NormalizationStatus,
)
from app.pipeline.normalization.anomaly import run_anomaly_checks
from app.pipeline.normalization.quality import compute_quality_report
from app.pipeline.normalization.stages.cleaning import clean_dict_values
from app.pipeline.normalization.stages.structuring import build_canonical_output


class NormalizationEngine:
    """
    Enterprise-grade forensic data normalization engine.

    Processes evidence files through a configurable pipeline:
    1. Validation — verify input data integrity
    2. Cleaning — text/encoding normalization
    3. Transformation — timestamps, units, locations
    4. Enrichment — medical terminology, abbreviation expansion
    5. Canonical Structuring — build standardized output
    6. Anomaly Pre-checks — detect data quality issues
    7. Quality Scoring — compute confidence/completeness metrics
    8. Persistence — store versioned, immutable results
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def normalize(
        self,
        evidence_file_id: str,
    ) -> dict[str, Any]:
        """
        Run the full normalization pipeline for a single evidence file.

        Args:
            evidence_file_id: UUID of the EvidenceFile to normalize.

        Returns:
            Dict with normalization results, quality report, anomalies.
        """
        start_time = time.monotonic()
        stage_reports: list[dict[str, Any]] = []

        # ── Load evidence file ───────────────
        evidence = (
            self.db.query(EvidenceFile)
            .filter(EvidenceFile.id == uuid.UUID(evidence_file_id))
            .first()
        )

        if not evidence:
            raise NormalizationError(
                f"Evidence file {evidence_file_id} not found",
                context={"evidence_file_id": evidence_file_id},
            )

        # ── Load metadata ────────────────────
        meta_records = (
            self.db.query(MetadataRecord)
            .filter(
                MetadataRecord.evidence_file_id == uuid.UUID(evidence_file_id)
            )
            .all()
        )

        # Merge all metadata into one dict
        raw_metadata: dict[str, Any] = {}
        for record in meta_records:
            if record.extracted_data:
                raw_metadata.update(record.extracted_data)

        logger.info(
            f"Starting normalization for evidence {evidence_file_id} "
            f"({evidence.original_filename})"
        )

        # ── Create normalization record ──────
        norm_record = NormalizationRecord(
            evidence_file_id=uuid.UUID(evidence_file_id),
            status=NormalizationStatus.IN_PROGRESS,
        )
        self.db.add(norm_record)
        self.db.flush()

        try:
            # ── Stage 1: Cleaning ────────────
            stage_start = time.monotonic()
            try:
                cleaned_metadata = clean_dict_values(raw_metadata)
                stage_reports.append({
                    "stage_name": "cleaning",
                    "status": "completed",
                    "duration_ms": round(
                        (time.monotonic() - stage_start) * 1000, 2
                    ),
                    "fields_processed": len(cleaned_metadata),
                    "fields_modified": self._count_diff(
                        raw_metadata, cleaned_metadata
                    ),
                })
            except Exception as e:
                stage_reports.append({
                    "stage_name": "cleaning",
                    "status": "failed",
                    "error": str(e),
                    "duration_ms": round(
                        (time.monotonic() - stage_start) * 1000, 2
                    ),
                })
                cleaned_metadata = raw_metadata

            # ── Stage 2: Canonical Structuring ─
            stage_start = time.monotonic()
            try:
                canonical = build_canonical_output(
                    evidence_file_id=evidence_file_id,
                    original_filename=evidence.original_filename,
                    mime_type=evidence.mime_type,
                    category=evidence.category.value if hasattr(evidence.category, 'value') else str(evidence.category),
                    file_size=evidence.file_size,
                    sha256_hash=evidence.sha256_hash,
                    metadata=cleaned_metadata,
                )
                stage_reports.append({
                    "stage_name": "structuring",
                    "status": "completed",
                    "duration_ms": round(
                        (time.monotonic() - stage_start) * 1000, 2
                    ),
                    "fields_processed": len(canonical),
                })
            except Exception as e:
                logger.error(f"Structuring stage failed: {e}")
                stage_reports.append({
                    "stage_name": "structuring",
                    "status": "failed",
                    "error": str(e),
                    "duration_ms": round(
                        (time.monotonic() - stage_start) * 1000, 2
                    ),
                })
                canonical = {
                    "source_evidence_id": evidence_file_id,
                    "raw_metadata": cleaned_metadata,
                    "error": str(e),
                }

            # ── Stage 3: Anomaly Pre-checks ──
            stage_start = time.monotonic()
            try:
                anomalies = run_anomaly_checks(
                    cleaned_metadata, canonical
                )
                stage_reports.append({
                    "stage_name": "anomaly_checks",
                    "status": "completed",
                    "duration_ms": round(
                        (time.monotonic() - stage_start) * 1000, 2
                    ),
                    "fields_processed": len(cleaned_metadata),
                    "warnings": [
                        a["description"] for a in anomalies
                    ],
                })
            except Exception as e:
                logger.error(f"Anomaly check failed: {e}")
                anomalies = []
                stage_reports.append({
                    "stage_name": "anomaly_checks",
                    "status": "failed",
                    "error": str(e),
                    "duration_ms": round(
                        (time.monotonic() - stage_start) * 1000, 2
                    ),
                })

            # ── Stage 4: Quality Scoring ─────
            stage_start = time.monotonic()
            try:
                quality_report = compute_quality_report(
                    evidence_file_id=evidence_file_id,
                    canonical=canonical,
                    anomalies=anomalies,
                    stage_reports=stage_reports,
                )
                stage_reports.append({
                    "stage_name": "quality_scoring",
                    "status": "completed",
                    "duration_ms": round(
                        (time.monotonic() - stage_start) * 1000, 2
                    ),
                })
            except Exception as e:
                logger.error(f"Quality scoring failed: {e}")
                quality_report = {
                    "overall_quality_score": 0.0,
                    "completeness_score": 0.0,
                    "confidence_score": 0.0,
                }
                stage_reports.append({
                    "stage_name": "quality_scoring",
                    "status": "failed",
                    "error": str(e),
                    "duration_ms": round(
                        (time.monotonic() - stage_start) * 1000, 2
                    ),
                })

            # ── Persist Results ──────────────
            completed_stages = [
                s["stage_name"]
                for s in stage_reports
                if s["status"] == "completed"
            ]
            failed_stages = [
                s["stage_name"]
                for s in stage_reports
                if s["status"] == "failed"
            ]

            has_failures = len(failed_stages) > 0
            norm_record.status = (
                NormalizationStatus.PARTIAL
                if has_failures
                else NormalizationStatus.COMPLETED
            )
            norm_record.canonical_output = canonical
            norm_record.quality_score = quality_report.get(
                "overall_quality_score", 0.0
            )
            norm_record.completeness_score = quality_report.get(
                "completeness_score", 0.0
            )
            norm_record.confidence_score = quality_report.get(
                "confidence_score", 0.0
            )
            norm_record.quality_report = quality_report
            norm_record.anomalies_detected = anomalies
            norm_record.anomaly_count = len(anomalies)
            norm_record.stages_completed = completed_stages
            norm_record.stages_failed = failed_stages
            norm_record.completed_at = datetime.now(timezone.utc)

            self.db.commit()

            elapsed = round(time.monotonic() - start_time, 3)
            logger.info(
                f"Normalization completed for {evidence_file_id} "
                f"in {elapsed}s — quality={norm_record.quality_score:.2f}, "
                f"anomalies={len(anomalies)}"
            )

            return {
                "normalization_id": str(norm_record.id),
                "evidence_file_id": evidence_file_id,
                "status": norm_record.status.value,
                "canonical_output": canonical,
                "quality_report": quality_report,
                "anomalies": anomalies,
                "stages_completed": completed_stages,
                "stages_failed": failed_stages,
                "elapsed_seconds": elapsed,
            }

        except Exception as e:
            norm_record.status = NormalizationStatus.FAILED
            norm_record.error_message = str(e)
            self.db.commit()

            logger.error(
                f"Normalization failed for {evidence_file_id}: {e}"
            )
            raise NormalizationError(
                f"Normalization failed: {e}",
                context={"evidence_file_id": evidence_file_id},
            ) from e

    def normalize_batch(
        self,
        evidence_file_ids: list[str],
    ) -> list[dict[str, Any]]:
        """Normalize multiple evidence files."""
        results: list[dict[str, Any]] = []
        for eid in evidence_file_ids:
            try:
                result = self.normalize(eid)
                results.append(result)
            except Exception as e:
                results.append({
                    "evidence_file_id": eid,
                    "status": "FAILED",
                    "error": str(e),
                })
        return results

    @staticmethod
    def _count_diff(
        original: dict[str, Any],
        cleaned: dict[str, Any],
    ) -> int:
        """Count how many values changed during cleaning."""
        count = 0
        for key in original:
            if key in cleaned and original[key] != cleaned[key]:
                count += 1
        return count
