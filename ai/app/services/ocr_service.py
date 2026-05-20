"""
Atopsy — OCR Service Facade.

High-level service interface over the forensic OCR pipeline.
Backward-compatible with existing callers while providing
full pipeline capabilities.
"""

from __future__ import annotations

from typing import Any

from app.core.logger import logger
from app.pipeline.ingestion.ocr.pipeline import OCRPipeline
from app.pipeline.ingestion.ocr.schemas import (
    DocumentOCRResult,
    OCRPageResult,
    OCRPipelineConfig,
)


# ─────────────────────────────────────────────
# Backward-Compatible Functions
# ─────────────────────────────────────────────


def extract_text_from_pdf(pdf_path: str) -> str:
    """
    Extract text from a PDF file.
    Backward-compatible with the original simple implementation.
    """
    try:
        import fitz
        text = ""
        document = fitz.open(pdf_path)
        for page in document:
            text += page.get_text()
        document.close()
        return text
    except Exception as e:
        logger.warning(f"Simple PDF extraction failed: {e}")
        return ""


def extract_text_from_image(image_path: str) -> str:
    """
    Extract text from an image file.
    Backward-compatible with the original simple implementation.
    """
    try:
        from PIL import Image
        import pytesseract
        image = Image.open(image_path)
        text = pytesseract.image_to_string(image)
        return text
    except Exception as e:
        logger.warning(f"Simple image extraction failed: {e}")
        return ""


# ─────────────────────────────────────────────
# Production OCR Service
# ─────────────────────────────────────────────


class OCRService:
    """
    Production OCR service facade for the Atopsy forensic pipeline.

    Provides high-level methods for document processing that
    delegate to the full OCR pipeline with preprocessing,
    layout analysis, engine selection, and field extraction.
    """

    _SUPPORTED_FORMATS = [
        ".pdf", ".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp",
    ]

    def __init__(
        self,
        config: OCRPipelineConfig | None = None,
    ) -> None:
        self.config = config or OCRPipelineConfig()
        self._pipeline = OCRPipeline(self.config)

    def process_document(
        self,
        file_path: str,
        document_id: str = "",
        config: OCRPipelineConfig | None = None,
    ) -> DocumentOCRResult:
        """
        Process a document through the full OCR pipeline.

        Includes: quality assessment, preprocessing, layout analysis,
        OCR (Tesseract + Gemini), and structured field extraction.

        Args:
            file_path: Path to the document file.
            document_id: Unique identifier for tracking.
            config: Optional override configuration.

        Returns:
            DocumentOCRResult with full text, structured fields,
            per-page results, and pipeline metadata.
        """
        try:
            return self._pipeline.process_document(
                file_path=file_path,
                document_id=document_id,
                config=config or self.config,
            )
        except Exception as e:
            logger.error(f"OCR service error: {e}")
            return DocumentOCRResult(
                document_id=document_id,
                warnings=[f"OCR processing failed: {str(e)}"],
            )

    def process_image(
        self,
        image_bytes: bytes,
        filename: str = "image",
    ) -> OCRPageResult:
        """
        Process a single image through OCR.

        Args:
            image_bytes: Raw image bytes.
            filename: Original filename for logging.

        Returns:
            OCRPageResult with text and confidence.
        """
        import tempfile
        import os
        from pathlib import Path

        try:
            # Write to temp file for pipeline processing
            suffix = Path(filename).suffix or ".png"
            with tempfile.NamedTemporaryFile(
                suffix=suffix, delete=False
            ) as tmp:
                tmp.write(image_bytes)
                tmp_path = tmp.name

            try:
                result = self._pipeline.process_document(
                    file_path=tmp_path,
                    document_id=filename,
                    config=self.config,
                )

                if result.pages:
                    return OCRPageResult(
                        text=result.full_text,
                        confidence=result.overall_confidence,
                        engine=result.pages[0].engine,
                        words=result.pages[0].words,
                        processing_time_ms=result.total_processing_time_ms,
                    )

                return OCRPageResult(text=result.full_text)
            finally:
                os.unlink(tmp_path)

        except Exception as e:
            logger.error(f"Image OCR failed for {filename}: {e}")
            return OCRPageResult()

    def get_supported_formats(self) -> list[str]:
        """Return list of supported file extensions."""
        return self._SUPPORTED_FORMATS.copy()

    def is_supported(self, filename: str) -> bool:
        """Check if a file format is supported."""
        from pathlib import Path
        suffix = Path(filename).suffix.lower()
        return suffix in self._SUPPORTED_FORMATS