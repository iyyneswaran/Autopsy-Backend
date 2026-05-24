"""
Atopsy — OCR & NLP Extraction Engine (Layer 3).

Orchestrates the extraction pipeline that transforms raw OCR output
(DocumentOCRResult from Layer 1) into structured intermediate data
(ExtractionEnvelope) for downstream entity structuring.

Pipeline stages:
  1. Text Assembly — layout-aware reconstruction
  2. NLP Extraction — rule-based + model-assisted
  3. Confidence Calibration — multi-source fusion
  4. Envelope Assembly — final packaging
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.logger import logger
from app.exceptions.pipeline import ExtractionError
from app.pipeline.ingestion.ocr.schemas import DocumentOCRResult
from app.pipeline.extraction.schemas import (
    AssembledDocument,
    ExtractionEnvelope,
    ExtractionMetadata,
    ExtractionStageReport,
    ExtractedSpan,
)
from app.pipeline.extraction.text_assembler import assemble_document
from app.pipeline.extraction.confidence import (
    calibrate_all,
    fuse_multi_source,
    flag_low_confidence,
)
from app.pipeline.extraction.nlp.regex_extractor import RegexExtractor
from app.pipeline.extraction.nlp.gemini_extractor import GeminiExtractor
from app.pipeline.extraction.nlp.section_detector import detect_sections
from app.pipeline.extraction.nlp.language_detector import detect_language


class ExtractionEngine:
    """
    OCR & NLP Extraction Engine — Layer 3.

    Processes DocumentOCRResult through a 4-stage pipeline:
    1. Text Assembly — layout-aware text reconstruction
    2. NLP Extraction — forensic entity span extraction
    3. Confidence Calibration — fusion and scoring
    4. Envelope Assembly — structured output packaging

    Each stage is independently fault-tolerant.
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self._regex_extractor = RegexExtractor()
        self._gemini_extractor = GeminiExtractor()

    def extract(
        self,
        document_ocr_result: DocumentOCRResult,
        evidence_file_id: str,
    ) -> dict[str, Any]:
        """
        Run the full extraction pipeline for a single document.

        Args:
            document_ocr_result: OCR output from the acquisition layer.
            evidence_file_id: UUID of the source EvidenceFile.

        Returns:
            Dict with extraction results, envelope, and stage reports.
        """
        start_time = time.monotonic()
        stage_reports: list[dict[str, Any]] = []

        logger.info(
            f"Starting extraction for evidence {evidence_file_id} "
            f"({document_ocr_result.page_count} pages)"
        )

        # Create DB record
        extraction_record = self._create_record(evidence_file_id)

        try:
            # ── Stage 1: Text Assembly ────────
            assembled = self._run_stage(
                "text_assembly",
                stage_reports,
                lambda: self._stage_text_assembly(document_ocr_result),
                fallback=AssembledDocument(
                    full_text=document_ocr_result.full_text
                ),
            )

            # ── Stage 2: NLP Extraction ───────
            spans = self._run_stage(
                "nlp_extraction",
                stage_reports,
                lambda: self._stage_nlp_extraction(assembled),
                fallback=[],
            )

            # ── Stage 3: Confidence Calibration ─
            calibrated_spans = self._run_stage(
                "confidence_calibration",
                stage_reports,
                lambda: self._stage_confidence_calibration(
                    spans, assembled, document_ocr_result
                ),
                fallback=spans,
            )

            # ── Stage 4: Envelope Assembly ────
            envelope = self._run_stage(
                "envelope_assembly",
                stage_reports,
                lambda: self._stage_envelope_assembly(
                    evidence_file_id,
                    document_ocr_result,
                    assembled,
                    calibrated_spans,
                    stage_reports,
                ),
                fallback=ExtractionEnvelope(
                    evidence_file_id=evidence_file_id,
                    assembled_document=assembled,
                    extracted_spans=calibrated_spans,
                ),
            )

            # ── Persist ──────────────────────
            elapsed = round(time.monotonic() - start_time, 3)
            self._update_record(
                extraction_record,
                envelope=envelope,
                stage_reports=stage_reports,
                elapsed_ms=elapsed * 1000,
                status="COMPLETED",
            )

            logger.info(
                f"Extraction completed for {evidence_file_id} in {elapsed}s "
                f"— {len(calibrated_spans)} spans extracted"
            )

            return {
                "extraction_id": str(extraction_record.id),
                "evidence_file_id": evidence_file_id,
                "status": "COMPLETED",
                "envelope": envelope.model_dump(),
                "stage_reports": stage_reports,
                "elapsed_seconds": elapsed,
            }

        except Exception as e:
            self._update_record(
                extraction_record,
                status="FAILED",
                error=str(e),
            )
            logger.error(f"Extraction failed for {evidence_file_id}: {e}")
            raise ExtractionError(
                f"Extraction failed: {e}",
                context={"evidence_file_id": evidence_file_id},
            ) from e

    # ─────────────────────────────────────────
    # Stage Implementations
    # ─────────────────────────────────────────

    def _stage_text_assembly(
        self,
        ocr_result: DocumentOCRResult,
    ) -> AssembledDocument:
        """Stage 1: Layout-aware text assembly."""
        return assemble_document(ocr_result)

    def _stage_nlp_extraction(
        self,
        assembled: AssembledDocument,
    ) -> list[ExtractedSpan]:
        """Stage 2: Run all NLP extractors."""
        all_spans: list[ExtractedSpan] = []
        text = assembled.full_text

        if not text or len(text.strip()) < 10:
            return all_spans

        # Detect sections and language for context
        sections = detect_sections(text)
        lang_info = detect_language(text)
        context = {
            "sections": sections,
            "language": lang_info,
        }

        # Run rule-based extraction (primary, deterministic)
        try:
            regex_spans = self._regex_extractor.extract(text, context)
            all_spans.extend(regex_spans)
        except Exception as e:
            logger.warning(f"Regex extraction failed: {e}")

        # Run Gemini extraction (fallback/enrichment)
        try:
            gemini_spans = self._gemini_extractor.extract(text, context)
            all_spans.extend(gemini_spans)
        except Exception as e:
            logger.warning(f"Gemini extraction failed: {e}")

        return all_spans

    def _stage_confidence_calibration(
        self,
        spans: list[ExtractedSpan],
        assembled: AssembledDocument,
        ocr_result: DocumentOCRResult,
    ) -> list[ExtractedSpan]:
        """Stage 3: Calibrate and fuse confidence scores."""
        # Build page confidence map
        page_confidences: dict[int, float] = {}
        for page in assembled.pages:
            page_confidences[page.page_number] = page.confidence

        # Calibrate each span with OCR confidence
        calibrated = calibrate_all(spans, page_confidences)

        # Fuse overlapping multi-source spans
        fused = fuse_multi_source(calibrated)

        # Flag low-confidence spans
        flagged = flag_low_confidence(fused, threshold=0.3)

        return flagged

    def _stage_envelope_assembly(
        self,
        evidence_file_id: str,
        ocr_result: DocumentOCRResult,
        assembled: AssembledDocument,
        spans: list[ExtractedSpan],
        stage_reports: list[dict[str, Any]],
    ) -> ExtractionEnvelope:
        """Stage 4: Assemble the ExtractionEnvelope."""
        # Compute overall confidence
        span_confs = [s.confidence for s in spans if s.confidence > 0]
        overall_conf = (
            round(sum(span_confs) / len(span_confs), 4)
            if span_confs else 0.0
        )

        # Collect extractor IDs used
        extractors_used = list({s.extractor_id for s in spans})

        metadata = ExtractionMetadata(
            evidence_file_id=evidence_file_id,
            document_id=ocr_result.document_id,
            extractors_used=extractors_used,
            total_spans=len(spans),
            overall_confidence=overall_conf,
            page_count=len(assembled.pages),
            warnings=list(ocr_result.warnings) if ocr_result.warnings else [],
        )

        report_models = [
            ExtractionStageReport(
                stage=r.get("stage_name", ""),
                status=r.get("status", "completed"),
                duration_ms=r.get("duration_ms", 0.0),
                detail=r.get("detail", ""),
                error=r.get("error"),
            )
            for r in stage_reports
        ]

        return ExtractionEnvelope(
            evidence_file_id=evidence_file_id,
            assembled_document=assembled,
            extracted_spans=spans,
            metadata=metadata,
            stage_reports=report_models,
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
            logger.error(f"Extraction stage '{stage_name}' failed: {e}")
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
        """Create an OCRExtractionRecord in the database."""
        try:
            from app.models.pipeline import OCRExtractionRecord, ExtractionStatus
            record = OCRExtractionRecord(
                evidence_file_id=uuid.UUID(evidence_file_id),
                status=ExtractionStatus.IN_PROGRESS,
            )
            self.db.add(record)
            self.db.flush()
            return record
        except Exception as e:
            logger.warning(f"Could not create extraction record: {e}")
            # Return a mock record for graceful degradation
            class _MockRecord:
                id = uuid.uuid4()
            return _MockRecord()

    def _update_record(
        self,
        record: Any,
        envelope: ExtractionEnvelope | None = None,
        stage_reports: list[dict[str, Any]] | None = None,
        elapsed_ms: float = 0.0,
        status: str = "COMPLETED",
        error: str | None = None,
    ) -> None:
        """Update the extraction record with results."""
        try:
            from app.models.pipeline import ExtractionStatus
            record.status = ExtractionStatus(status)
            if envelope:
                record.extraction_envelope = envelope.model_dump()
                record.total_spans = envelope.metadata.total_spans
                record.overall_confidence = envelope.metadata.overall_confidence
                record.page_count = envelope.metadata.page_count
                record.extractors_used = envelope.metadata.extractors_used
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
        except Exception as e:
            logger.warning(f"Could not update extraction record: {e}")
