"""
Atopsy — OCR Pipeline Orchestrator.

Coordinates the full document OCR pipeline:
  Load → Quality Assessment → Preprocess → Layout Analysis →
  OCR (Tesseract/Gemini) → Field Extraction → Result Assembly

Each stage is independently fault-tolerant.
"""

from __future__ import annotations

import io
import time
from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np
from PIL import Image

from app.core.logger import logger
from app.pipeline.ingestion.ocr.schemas import (
    ContentType,
    DocumentOCRResult,
    OCREngine,
    OCRPageResult,
    OCRPipelineConfig,
    PageOCRResult,
    PipelineStage,
    PreprocessResult,
    ProcessingStageReport,
    QualityAssessment,
)


ProgressCallback = Callable[[str, float], None] | None


class OCRPipeline:
    """
    Main OCR pipeline orchestrator for forensic documents.

    Processes PDF and image files through a configurable
    multi-stage pipeline with automatic engine selection.
    """

    def __init__(
        self,
        config: OCRPipelineConfig | None = None,
    ) -> None:
        self.config = config or OCRPipelineConfig()
        self._stages: list[ProcessingStageReport] = []

    def process_document(
        self,
        file_path: str,
        document_id: str = "",
        config: OCRPipelineConfig | None = None,
        progress_callback: ProgressCallback = None,
    ) -> DocumentOCRResult:
        """
        Process a complete document through the OCR pipeline.

        Args:
            file_path: Path to the document file.
            document_id: Unique identifier for tracking.
            config: Optional override configuration.
            progress_callback: Optional callback(stage_name, progress_pct).

        Returns:
            DocumentOCRResult with full text, per-page results,
            structured fields, and pipeline metadata.
        """
        cfg = config or self.config
        self._stages = []
        pipeline_start = time.monotonic()
        warnings: list[str] = []
        engines_used: set[str] = set()

        # ── Stage 1: Load Document ───────────────
        self._notify(progress_callback, "Loading document", 0.0)
        stage_start = time.monotonic()

        try:
            pages = self._load_document(file_path, cfg.max_pages)
            self._record_stage(
                PipelineStage.LOADING, "completed",
                time.monotonic() - stage_start,
                f"Loaded {len(pages)} pages",
            )
        except Exception as e:
            self._record_stage(
                PipelineStage.LOADING, "failed",
                time.monotonic() - stage_start,
                error=str(e),
            )
            logger.error(f"Document loading failed: {e}")
            return self._build_empty_result(document_id, str(e))

        if not pages:
            return self._build_empty_result(document_id, "No pages found")

        # ── Process Each Page ────────────────────
        page_results: list[PageOCRResult] = []
        all_text_parts: list[str] = []
        overall_quality = QualityAssessment()

        for page_num, page_image in enumerate(pages):
            page_pct = (page_num / len(pages)) * 100
            self._notify(
                progress_callback,
                f"Processing page {page_num + 1}/{len(pages)}",
                page_pct,
            )

            page_result = self._process_page(
                page_image, page_num, cfg, engines_used
            )
            page_results.append(page_result)

            if page_result.text.strip():
                all_text_parts.append(page_result.text)

            if page_result.quality.overall_score > overall_quality.overall_score:
                overall_quality = page_result.quality

        full_text = "\n\n--- Page Break ---\n\n".join(all_text_parts)

        # ── Stage: Field Extraction ──────────────
        self._notify(progress_callback, "Extracting structured fields", 85.0)
        stage_start = time.monotonic()
        structured_fields = None

        if full_text.strip():
            try:
                from app.pipeline.ingestion.ocr import field_extractor

                # Try Gemini structured extraction on full text
                gemini_data = {}
                if cfg.use_gemini_for_handwriting:
                    try:
                        from app.pipeline.ingestion.ocr import gemini_engine
                        gemini_data = gemini_engine.extract_text_from_full_text(
                            full_text, cfg.gemini
                        )
                    except Exception as ge:
                        logger.warning(f"Gemini text extraction failed: {ge}")

                structured_fields = field_extractor.extract_fields(
                    full_text,
                    structured_data=gemini_data,
                )

                self._record_stage(
                    PipelineStage.FIELD_EXTRACTION, "completed",
                    time.monotonic() - stage_start,
                    f"Confidence: {structured_fields.extraction_confidence:.2f}",
                )
            except Exception as e:
                logger.warning(f"Field extraction failed: {e}")
                self._record_stage(
                    PipelineStage.FIELD_EXTRACTION, "failed",
                    time.monotonic() - stage_start,
                    error=str(e),
                )
        else:
            self._record_stage(
                PipelineStage.FIELD_EXTRACTION, "skipped",
                0.0, "No text to extract from",
            )

        # ── Stage: Result Assembly ───────────────
        self._notify(progress_callback, "Assembling results", 95.0)

        # Compute overall confidence
        page_confidences = [p.confidence for p in page_results if p.confidence > 0]
        overall_confidence = (
            sum(page_confidences) / len(page_confidences)
            if page_confidences
            else 0.0
        )

        total_time = round((time.monotonic() - pipeline_start) * 1000, 2)

        self._record_stage(
            PipelineStage.RESULT_ASSEMBLY, "completed",
            0.0, f"Total: {total_time:.0f}ms",
        )

        result = DocumentOCRResult(
            document_id=document_id,
            full_text=full_text,
            overall_confidence=round(overall_confidence, 4),
            page_count=len(pages),
            pages=page_results,
            structured_fields=structured_fields,
            quality_summary=overall_quality,
            pipeline_stages=self._stages,
            total_processing_time_ms=total_time,
            engines_used=sorted(engines_used),
            warnings=warnings,
        )

        self._notify(progress_callback, "Complete", 100.0)

        logger.info(
            f"OCR pipeline complete: {document_id}, "
            f"{len(pages)} pages, {len(full_text)} chars, "
            f"confidence={overall_confidence:.2f}, {total_time:.0f}ms"
        )

        return result

    # ─────────────────────────────────────────
    # Page Processing
    # ─────────────────────────────────────────

    def _process_page(
        self,
        image: np.ndarray,
        page_num: int,
        cfg: OCRPipelineConfig,
        engines_used: set[str],
    ) -> PageOCRResult:
        """Process a single page through the pipeline stages."""

        # Quality Assessment
        try:
            from app.pipeline.ingestion.ocr import quality_assessor
            quality = quality_assessor.assess_quality(image)
        except Exception as e:
            logger.warning(f"Quality assessment failed p{page_num}: {e}")
            quality = QualityAssessment()

        # Preprocessing
        preprocess = PreprocessResult()
        processed = image
        try:
            from app.pipeline.ingestion.ocr import preprocessor
            processed, preprocess = preprocessor.preprocess_image(
                image, cfg.preprocess
            )
        except Exception as e:
            logger.warning(f"Preprocessing failed p{page_num}: {e}")

        # Layout Analysis
        try:
            from app.pipeline.ingestion.ocr import layout_analyzer
            layout = layout_analyzer.analyze_layout(processed)
        except Exception as e:
            logger.warning(f"Layout analysis failed p{page_num}: {e}")
            from app.pipeline.ingestion.ocr.schemas import LayoutAnalysis
            layout = LayoutAnalysis()

        # OCR Execution
        page_text = ""
        page_confidence = 0.0
        page_engine = OCREngine.TESSERACT
        page_words = []

        if layout.regions:
            # Process each region with appropriate engine
            region_texts: list[str] = []
            region_confidences: list[float] = []

            for region in sorted(layout.regions, key=lambda r: r.reading_order):
                bbox = region.bbox
                roi = processed[
                    bbox.y:bbox.y + bbox.h,
                    bbox.x:bbox.x + bbox.w
                ]
                if roi.size == 0:
                    continue

                # Select engine based on content type
                if (
                    region.content_type == ContentType.HANDWRITTEN
                    and cfg.use_gemini_for_handwriting
                ):
                    ocr_result = self._run_gemini_ocr(roi, cfg)
                    engines_used.add("GEMINI")
                else:
                    ocr_result = self._run_tesseract_ocr(
                        roi, cfg, region.content_type
                    )
                    engines_used.add("TESSERACT")

                if ocr_result.text.strip():
                    region_texts.append(ocr_result.text)
                    region_confidences.append(ocr_result.confidence)
                    page_words.extend(ocr_result.words)

            page_text = "\n".join(region_texts)
            if region_confidences:
                page_confidence = sum(region_confidences) / len(region_confidences)
        else:
            # No layout regions — process whole page
            ocr_result = self._run_tesseract_ocr(
                processed, cfg, ContentType.UNKNOWN
            )
            engines_used.add("TESSERACT")
            page_text = ocr_result.text
            page_confidence = ocr_result.confidence
            page_words = ocr_result.words
            page_engine = ocr_result.engine

            # If Tesseract confidence is low, try Gemini
            if (
                page_confidence < cfg.gemini_confidence_threshold
                and cfg.use_gemini_for_handwriting
            ):
                gemini_result = self._run_gemini_ocr(processed, cfg)
                if gemini_result.confidence > page_confidence:
                    page_text = gemini_result.text
                    page_confidence = gemini_result.confidence
                    page_engine = OCREngine.GEMINI
                    engines_used.add("GEMINI")

        return PageOCRResult(
            page_number=page_num + 1,
            text=page_text,
            confidence=round(page_confidence, 4),
            engine=page_engine,
            quality=quality,
            preprocess=preprocess,
            layout=layout,
            words=page_words,
        )

    # ─────────────────────────────────────────
    # Engine Runners
    # ─────────────────────────────────────────

    def _run_tesseract_ocr(
        self,
        image: np.ndarray,
        cfg: OCRPipelineConfig,
        content_type: ContentType,
    ) -> OCRPageResult:
        """Run Tesseract OCR on an image."""
        try:
            from app.pipeline.ingestion.ocr import tesseract_engine
            return tesseract_engine.extract_text(
                image, cfg.tesseract, content_type
            )
        except Exception as e:
            logger.error(f"Tesseract OCR error: {e}")
            return OCRPageResult(engine=OCREngine.TESSERACT)

    def _run_gemini_ocr(
        self,
        image: np.ndarray,
        cfg: OCRPipelineConfig,
    ) -> OCRPageResult:
        """Run Gemini Vision OCR on an image."""
        try:
            from app.pipeline.ingestion.ocr import gemini_engine
            image_bytes = gemini_engine.numpy_to_bytes(image)
            return gemini_engine.extract_text(image_bytes, cfg.gemini)
        except Exception as e:
            logger.error(f"Gemini OCR error: {e}")
            return OCRPageResult(engine=OCREngine.GEMINI)

    # ─────────────────────────────────────────
    # Document Loading
    # ─────────────────────────────────────────

    def _load_document(
        self,
        file_path: str,
        max_pages: int = 200,
    ) -> list[np.ndarray]:
        """
        Load a document as a list of page images.
        Supports PDF (via PyMuPDF) and single images.
        """
        path = Path(file_path)
        suffix = path.suffix.lower()

        if suffix == ".pdf":
            return self._load_pdf_pages(file_path, max_pages)
        elif suffix in (".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp"):
            return self._load_single_image(file_path)
        else:
            # Try as image
            try:
                return self._load_single_image(file_path)
            except Exception:
                raise ValueError(f"Unsupported document format: {suffix}")

    def _load_pdf_pages(
        self,
        file_path: str,
        max_pages: int,
    ) -> list[np.ndarray]:
        """Load PDF pages as images using PyMuPDF."""
        try:
            import fitz  # PyMuPDF

            doc = fitz.open(file_path)
            pages: list[np.ndarray] = []

            page_count = min(doc.page_count, max_pages)

            for i in range(page_count):
                page = doc[i]
                # Render at 300 DPI
                mat = fitz.Matrix(300 / 72, 300 / 72)
                pix = page.get_pixmap(matrix=mat)

                # Convert to numpy array
                img_data = pix.tobytes("png")
                nparr = np.frombuffer(img_data, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

                if img is not None:
                    pages.append(img)

            doc.close()
            return pages

        except ImportError:
            logger.warning("PyMuPDF not available, trying pdfplumber")
            return self._load_pdf_pdfplumber(file_path, max_pages)

    def _load_pdf_pdfplumber(
        self,
        file_path: str,
        max_pages: int,
    ) -> list[np.ndarray]:
        """Fallback PDF loading using pdfplumber + Pillow."""
        try:
            import pdfplumber

            pages: list[np.ndarray] = []
            with pdfplumber.open(file_path) as pdf:
                for i, page in enumerate(pdf.pages[:max_pages]):
                    img = page.to_image(resolution=300)
                    pil_img = img.original
                    np_img = np.array(pil_img)
                    if len(np_img.shape) == 3 and np_img.shape[2] == 4:
                        np_img = cv2.cvtColor(np_img, cv2.COLOR_RGBA2BGR)
                    elif len(np_img.shape) == 3:
                        np_img = cv2.cvtColor(np_img, cv2.COLOR_RGB2BGR)
                    pages.append(np_img)

            return pages

        except Exception as e:
            raise RuntimeError(f"Cannot load PDF: {e}")

    def _load_single_image(
        self,
        file_path: str,
    ) -> list[np.ndarray]:
        """Load a single image file."""
        img = cv2.imread(file_path, cv2.IMREAD_COLOR)
        if img is None:
            # Try with Pillow
            try:
                pil_img = Image.open(file_path)
                img = np.array(pil_img)
                if len(img.shape) == 3 and img.shape[2] == 4:
                    img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
                elif len(img.shape) == 3:
                    img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
            except Exception as e:
                raise ValueError(f"Cannot load image {file_path}: {e}")

        return [img]

    # ─────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────

    def _record_stage(
        self,
        stage: PipelineStage,
        status: str,
        duration_s: float,
        detail: str = "",
        error: str | None = None,
    ) -> None:
        self._stages.append(ProcessingStageReport(
            stage=stage,
            status=status,
            duration_ms=round(duration_s * 1000, 2),
            detail=detail,
            error=error,
        ))

    def _notify(
        self,
        callback: ProgressCallback,
        stage: str,
        pct: float,
    ) -> None:
        if callback:
            try:
                callback(stage, pct)
            except Exception:
                pass

    def _build_empty_result(
        self,
        document_id: str,
        error: str,
    ) -> DocumentOCRResult:
        return DocumentOCRResult(
            document_id=document_id,
            pipeline_stages=self._stages,
            warnings=[f"Pipeline failed: {error}"],
        )
