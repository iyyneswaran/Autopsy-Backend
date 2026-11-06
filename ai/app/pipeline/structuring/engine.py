"""
Atopsy — Forensic Entity Structuring Engine (Layer 4).

Orchestrates the structuring pipeline that transforms extraction
output (ExtractionEnvelope from Layer 3) into a canonical forensic
entity graph (ForensicEntityGraph) for downstream intelligence layers.

Pipeline stages:
  1. Entity Mapping — span-to-entity conversion
  2. Value Normalization — canonical value standardization
  3. Provenance Assembly — provenance chain validation
  4. Confidence Aggregation — multi-stage confidence scoring
  5. Validation & Graph Assembly — validation + final packaging
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.logger import logger
from app.exceptions.pipeline import EntityStructuringError
from app.pipeline.extraction.schemas import ExtractionEnvelope
from app.pipeline.structuring.schemas import (
    EntityGraphMetrics,
    EntityNormalizationStatus,
    ForensicEntityGraph,
    StructuredEntity,
    StructuringStageReport,
)
from app.pipeline.structuring.entity_mapper import EntityMapper
from app.pipeline.structuring.value_normalizer import ValueNormalizer
from app.pipeline.structuring.provenance_tracker import ProvenanceTracker
from app.pipeline.structuring.confidence_aggregator import ConfidenceAggregator
from app.pipeline.structuring.validators import EntityValidator


class StructuringEngine:
    """
    Forensic Entity Structuring Engine — Layer 4.

    Processes ExtractionEnvelope through a 5-stage pipeline:
    1. Entity Mapping — ExtractedSpan → StructuredEntity
    2. Value Normalization — canonical value standardization
    3. Provenance Assembly — chain validation and enrichment
    4. Confidence Aggregation — final confidence scoring
    5. Validation & Graph Assembly — validation + packaging

    Each stage is independently fault-tolerant.
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self._mapper = EntityMapper()
        self._normalizer = ValueNormalizer()
        self._provenance = ProvenanceTracker()
        self._confidence = ConfidenceAggregator()
        self._validator = EntityValidator()

    def structure(
        self,
        envelope: ExtractionEnvelope,
        evidence_file_id: str,
    ) -> dict[str, Any]:
        """
        Run the full structuring pipeline.

        Args:
            envelope: Extraction output from Layer 3.
            evidence_file_id: UUID of the source EvidenceFile.

        Returns:
            Dict with structuring results, entity graph, stage reports.
        """
        start_time = time.monotonic()
        stage_reports: list[dict[str, Any]] = []

        logger.info(
            f"Starting entity structuring for {evidence_file_id} "
            f"({len(envelope.extracted_spans)} spans)"
        )

        # Create DB record
        structuring_record = self._create_record(evidence_file_id)

        try:
            # ── Stage 1: Entity Mapping ──────
            entities = self._run_stage(
                "entity_mapping",
                stage_reports,
                lambda: self._mapper.map_spans(envelope.extracted_spans),
                fallback=[],
            )

            # ── Stage 2: Value Normalization ─
            normalized = self._run_stage(
                "value_normalization",
                stage_reports,
                lambda: self._normalizer.normalize_entities(entities),
                fallback=entities,
            )

            # ── Stage 3: Provenance Assembly ─
            with_provenance = self._run_stage(
                "provenance_assembly",
                stage_reports,
                lambda: self._provenance.enrich_all(normalized),
                fallback=normalized,
            )

            # ── Stage 4: Confidence Aggregation
            ocr_conf = envelope.assembled_document.average_confidence
            scored = self._run_stage(
                "confidence_aggregation",
                stage_reports,
                lambda: self._confidence.aggregate(with_provenance, ocr_conf),
                fallback=with_provenance,
            )

            # ── Stage 5: Validation & Assembly
            graph = self._run_stage(
                "validation_and_assembly",
                stage_reports,
                lambda: self._stage_validate_and_assemble(
                    scored, evidence_file_id, stage_reports
                ),
                fallback=ForensicEntityGraph(
                    evidence_file_id=evidence_file_id,
                ),
            )

            # ── Persist ──────────────────────
            elapsed = round(time.monotonic() - start_time, 3)
            self._update_record(
                structuring_record,
                graph=graph,
                stage_reports=stage_reports,
                elapsed_ms=elapsed * 1000,
                status="PARTIAL" if any(r["status"] == "failed" for r in stage_reports) else "COMPLETED",
            )

            logger.info(
                f"Structuring completed for {evidence_file_id} in {elapsed}s "
                f"— {graph.metrics.total_entities} entities, "
                f"confidence={graph.metrics.average_confidence:.3f}"
            )

            return {
                "structuring_id": str(structuring_record.id),
                "evidence_file_id": evidence_file_id,
                "status": "PARTIAL" if any(r["status"] == "failed" for r in stage_reports) else "COMPLETED",
                "entity_graph": graph.model_dump(mode="json"),
                "stage_reports": stage_reports,
                "elapsed_seconds": elapsed,
            }

        except Exception as e:
            self._update_record(
                structuring_record,
                status="FAILED",
                error=str(e),
            )
            logger.error(f"Structuring failed for {evidence_file_id}: {e}")
            raise EntityStructuringError(
                f"Entity structuring failed: {e}",
                context={"evidence_file_id": evidence_file_id},
            ) from e

    # ─────────────────────────────────────────
    # Stage 5: Validate & Assemble Graph
    # ─────────────────────────────────────────

    def _stage_validate_and_assemble(
        self,
        entities: list[StructuredEntity],
        evidence_file_id: str,
        stage_reports: list[dict[str, Any]],
    ) -> ForensicEntityGraph:
        """Run validation and assemble the final entity graph."""
        # Validate
        validated = self._validator.validate_all(entities)

        # Group entities by type
        grouped: dict[str, list[StructuredEntity]] = {}
        for entity in validated:
            key = entity.entity_type.value
            grouped.setdefault(key, []).append(entity)

        # Compute metrics
        type_counts = {k: len(v) for k, v in grouped.items()}
        total = len(validated)
        avg_conf = self._confidence.compute_graph_confidence(validated)

        norm_count = sum(
            1 for e in validated
            if e.normalization_status in (
                EntityNormalizationStatus.NORMALIZED,
                EntityNormalizationStatus.VALIDATED,
            )
        )
        valid_count = sum(
            1 for e in validated
            if e.normalization_status == EntityNormalizationStatus.VALIDATED
        )
        prov_depths = [
            len(e.provenance.transformations) for e in validated
        ]
        avg_depth = (
            round(sum(prov_depths) / len(prov_depths), 2)
            if prov_depths else 0.0
        )

        metrics = EntityGraphMetrics(
            total_entities=total,
            entity_type_counts=type_counts,
            average_confidence=avg_conf,
            normalization_coverage=(
                round(norm_count / total, 4) if total > 0 else 0.0
            ),
            validation_pass_rate=(
                round(valid_count / total, 4) if total > 0 else 0.0
            ),
            provenance_depth_avg=avg_depth,
        )

        # Build stage report models
        reports = [
            StructuringStageReport(
                stage=r.get("stage_name", ""),
                status=r.get("status", "completed"),
                duration_ms=r.get("duration_ms", 0.0),
                entities_processed=total,
                detail=r.get("detail", ""),
                error=r.get("error"),
            )
            for r in stage_reports
        ]

        return ForensicEntityGraph(
            evidence_file_id=evidence_file_id,
            entities=grouped,
            metrics=metrics,
            stage_reports=reports,
        )

    # ─────────────────────────────────────────
    # Stage Runner
    # ─────────────────────────────────────────

    def _run_stage(
        self,
        stage_name: str,
        stage_reports: list[dict[str, Any]],
        fn: Any,
        fallback: Any = None,
    ) -> Any:
        """Execute a pipeline stage with timing and error handling."""
        stage_start = time.monotonic()
        try:
            result = fn()
            elapsed = round((time.monotonic() - stage_start) * 1000, 2)
            stage_reports.append({
                "stage_name": stage_name,
                "status": "completed",
                "duration_ms": elapsed,
            })
            return result if result is not None else fallback
        except Exception as e:
            elapsed = round((time.monotonic() - stage_start) * 1000, 2)
            logger.error(f"Structuring stage '{stage_name}' failed: {e}")
            stage_reports.append({
                "stage_name": stage_name,
                "status": "failed",
                "error": str(e),
                "duration_ms": elapsed,
            })
            return fallback

    # ─────────────────────────────────────────
    # DB Helpers
    # ─────────────────────────────────────────

    def _create_record(self, evidence_file_id: str) -> Any:
        """Create a ForensicEntityRecord in the database."""
        try:
            from app.models.pipeline import ForensicEntityRecord, ExtractionStatus
            record = ForensicEntityRecord(
                evidence_file_id=uuid.UUID(evidence_file_id),
                status=ExtractionStatus.IN_PROGRESS,
            )
            self.db.add(record)
            self.db.flush()
            return record
        except Exception:
            self.db.rollback()
            raise

    def _update_record(
        self,
        record: Any,
        graph: ForensicEntityGraph | None = None,
        stage_reports: list[dict[str, Any]] | None = None,
        elapsed_ms: float = 0.0,
        status: str = "COMPLETED",
        error: str | None = None,
    ) -> None:
        """Update the entity record with results."""
        try:
            from app.models.pipeline import ExtractionStatus
            record.status = ExtractionStatus(status)
            if graph:
                record.entity_graph = graph.model_dump(mode="json")
                record.entity_count = graph.metrics.total_entities
                record.entity_types_found = list(graph.metrics.entity_type_counts.keys())
                record.overall_confidence = graph.metrics.average_confidence
                record.provenance_depth = int(graph.metrics.provenance_depth_avg)
                record.validation_passed = graph.metrics.validation_pass_rate > 0.5
            if stage_reports:
                completed = [s["stage_name"] for s in stage_reports if s["status"] == "completed"]
                failed = [s["stage_name"] for s in stage_reports if s["status"] == "failed"]
                record.stages_completed = completed
                record.stages_failed = failed
            record.processing_time_ms = elapsed_ms
            if error:
                record.error_message = error
            if status in ("COMPLETED", "PARTIAL"):
                record.completed_at = datetime.now(timezone.utc)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
