"""
Atopsy — Layout-Aware Text Assembly.

Converts DocumentOCRResult (Layer 1 output) into an AssembledDocument
with page-level, line-level, and token-level metadata preserved.
Reconstructs reading order from layout regions and propagates
confidence scores through the hierarchy.
"""

from __future__ import annotations

import time
from typing import Any

from app.core.logger import logger
from app.pipeline.ingestion.ocr.schemas import (
    DocumentOCRResult,
    PageOCRResult,
    OCRLine,
    OCRWord,
)
from app.pipeline.extraction.schemas import (
    AssembledDocument,
    PageText,
    LineMetadata,
    TokenMetadata,
)


def assemble_document(ocr_result: DocumentOCRResult) -> AssembledDocument:
    """
    Assemble a layout-aware document from OCR page results.

    Reconstructs text with reading order, preserving line-level
    and token-level metadata from OCR word/line output.

    Args:
        ocr_result: DocumentOCRResult from the acquisition layer.

    Returns:
        AssembledDocument with full text hierarchy.
    """
    start = time.monotonic()
    pages: list[PageText] = []
    all_text_parts: list[str] = []
    total_lines = 0
    total_tokens = 0
    confidence_sum = 0.0
    confidence_count = 0
    languages: set[str] = set()
    content_types: set[str] = set()

    for page_ocr in ocr_result.pages:
        page_text = _assemble_page(page_ocr)
        pages.append(page_text)
        all_text_parts.append(page_text.text)

        total_lines += len(page_text.lines)
        for line in page_text.lines:
            total_tokens += len(line.tokens)

        if page_text.confidence > 0:
            confidence_sum += page_text.confidence
            confidence_count += 1

        if page_text.language:
            languages.add(page_text.language)
        if page_text.content_type and page_text.content_type != "UNKNOWN":
            content_types.add(page_text.content_type)

    avg_confidence = (
        round(confidence_sum / confidence_count, 4)
        if confidence_count > 0
        else 0.0
    )

    elapsed_ms = round((time.monotonic() - start) * 1000, 2)

    doc = AssembledDocument(
        full_text="\n\n".join(all_text_parts),
        pages=pages,
        total_lines=total_lines,
        total_tokens=total_tokens,
        average_confidence=avg_confidence,
        languages_detected=sorted(languages),
        content_types=sorted(content_types),
        assembly_time_ms=elapsed_ms,
    )

    logger.debug(
        f"Assembled document: {len(pages)} pages, "
        f"{total_lines} lines, {total_tokens} tokens, "
        f"confidence={avg_confidence:.3f}, {elapsed_ms:.1f}ms"
    )
    return doc


def _assemble_page(page_ocr: PageOCRResult) -> PageText:
    """Assemble a single page from OCR data."""
    lines: list[LineMetadata] = []

    # Prefer structured lines from OCR output
    if page_ocr.words:
        lines = _build_lines_from_words(page_ocr)
    elif page_ocr.text:
        lines = _build_lines_from_text(page_ocr)

    page_text = "\n".join(line.text for line in lines)

    # Determine content type from layout data
    content_type = "UNKNOWN"
    if hasattr(page_ocr, "layout") and page_ocr.layout:
        ct = page_ocr.layout.dominant_content_type
        content_type = ct.value if hasattr(ct, "value") else str(ct)

    # Detect language from OCR output
    language = ""
    engine_name = ""
    if hasattr(page_ocr, "engine") and page_ocr.engine:
        engine_name = (
            page_ocr.engine.value
            if hasattr(page_ocr.engine, "value")
            else str(page_ocr.engine)
        )

    # Compute page confidence from lines
    line_confidences = [l.confidence for l in lines if l.confidence > 0]
    page_confidence = (
        round(sum(line_confidences) / len(line_confidences), 4)
        if line_confidences
        else page_ocr.confidence
    )

    return PageText(
        page_number=page_ocr.page_number,
        text=page_text,
        lines=lines,
        confidence=page_confidence,
        content_type=content_type,
        language=language,
        ocr_engine=engine_name,
    )


def _build_lines_from_words(page_ocr: PageOCRResult) -> list[LineMetadata]:
    """Build line metadata from OCR word-level data."""
    lines: list[LineMetadata] = []

    # Group words by approximate Y-coordinate to form lines
    if not page_ocr.words:
        return lines

    # Sort words by vertical position then horizontal
    sorted_words = sorted(
        page_ocr.words,
        key=lambda w: (w.bbox.y if w.bbox else 0, w.bbox.x if w.bbox else 0),
    )

    current_line_words: list[OCRWord] = []
    current_y = -1
    line_threshold = 15  # pixels of Y-tolerance for same line

    for word in sorted_words:
        word_y = word.bbox.y if word.bbox else 0
        if current_y < 0:
            current_y = word_y

        if abs(word_y - current_y) > line_threshold and current_line_words:
            lines.append(
                _words_to_line(current_line_words, page_ocr.page_number, len(lines))
            )
            current_line_words = []
            current_y = word_y

        current_line_words.append(word)

    if current_line_words:
        lines.append(
            _words_to_line(current_line_words, page_ocr.page_number, len(lines))
        )

    return lines


def _words_to_line(
    words: list[OCRWord], page: int, line_idx: int
) -> LineMetadata:
    """Convert a list of OCR words into a single LineMetadata."""
    # Sort words left-to-right
    sorted_w = sorted(words, key=lambda w: w.bbox.x if w.bbox else 0)

    tokens = [
        TokenMetadata(
            text=w.text,
            confidence=w.confidence,
            bbox={
                "x": w.bbox.x, "y": w.bbox.y,
                "w": w.bbox.w, "h": w.bbox.h,
            } if w.bbox else None,
            page=page,
            line_idx=line_idx,
        )
        for w in sorted_w
    ]

    text = " ".join(t.text for t in tokens if t.text)
    confidences = [t.confidence for t in tokens if t.confidence > 0]
    avg_conf = (
        round(sum(confidences) / len(confidences), 4)
        if confidences else 0.0
    )

    # Compute bounding box for the line
    bbox = None
    if sorted_w and sorted_w[0].bbox:
        min_x = min(w.bbox.x for w in sorted_w if w.bbox)
        min_y = min(w.bbox.y for w in sorted_w if w.bbox)
        max_x = max(w.bbox.x + w.bbox.w for w in sorted_w if w.bbox)
        max_y = max(w.bbox.y + w.bbox.h for w in sorted_w if w.bbox)
        bbox = {"x": min_x, "y": min_y, "w": max_x - min_x, "h": max_y - min_y}

    return LineMetadata(
        text=text,
        tokens=tokens,
        confidence=avg_conf,
        bbox=bbox,
        page=page,
        line_number=line_idx,
        content_type="UNKNOWN",
    )


def _build_lines_from_text(page_ocr: PageOCRResult) -> list[LineMetadata]:
    """Fallback: build line metadata from raw text split."""
    lines: list[LineMetadata] = []
    for idx, raw_line in enumerate(page_ocr.text.split("\n")):
        stripped = raw_line.strip()
        if not stripped:
            continue
        tokens = [
            TokenMetadata(
                text=word,
                confidence=page_ocr.confidence,
                page=page_ocr.page_number,
                line_idx=idx,
            )
            for word in stripped.split()
        ]
        lines.append(LineMetadata(
            text=stripped,
            tokens=tokens,
            confidence=page_ocr.confidence,
            page=page_ocr.page_number,
            line_number=idx,
        ))
    return lines
