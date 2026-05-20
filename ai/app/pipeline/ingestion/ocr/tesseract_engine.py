"""
Atopsy — Production Tesseract OCR Engine.

Wraps pytesseract with adaptive configuration, word-level
confidence extraction, bounding boxes, and line grouping.
Optimized for forensic document processing with Hindi+English support.
"""

from __future__ import annotations

import time
from typing import Any

import numpy as np
import pytesseract
from PIL import Image

from app.core.logger import logger
from app.pipeline.ingestion.ocr.schemas import (
    BoundingBox,
    ContentType,
    OCREngine,
    OCRLine,
    OCRPageResult,
    OCRWord,
    TesseractConfig,
)


def extract_text(
    image: np.ndarray,
    config: TesseractConfig | None = None,
    content_type: ContentType = ContentType.UNKNOWN,
) -> OCRPageResult:
    """
    Extract text from an image using Tesseract OCR.

    Args:
        image: Grayscale or BGR numpy array.
        config: Tesseract configuration options.
        content_type: Hint about whether content is printed/handwritten.

    Returns:
        OCRPageResult with text, confidence, words, and lines.
    """
    cfg = config or TesseractConfig()
    start = time.monotonic()

    # Adaptive PSM selection based on content type
    psm = _select_psm(cfg.psm, content_type, image.shape)

    # Build tesseract config string
    tess_config = f"--oem {cfg.oem} --psm {psm}"
    if cfg.dpi:
        tess_config += f" --dpi {cfg.dpi}"
    if cfg.whitelist:
        tess_config += f" -c tessedit_char_whitelist={cfg.whitelist}"

    # Convert numpy to PIL Image
    pil_image = Image.fromarray(image)

    try:
        # Get word-level data with confidences and bounding boxes
        data = pytesseract.image_to_data(
            pil_image,
            lang=cfg.languages,
            config=tess_config,
            output_type=pytesseract.Output.DICT,
        )

        words = _extract_words(data)
        lines = _group_words_into_lines(words, data)
        full_text = "\n".join(line.text for line in lines if line.text.strip())

        # Compute overall confidence
        word_confidences = [w.confidence for w in words if w.confidence > 0]
        if word_confidences:
            overall_confidence = sum(word_confidences) / len(word_confidences)
        else:
            overall_confidence = 0.0

        # Detect language from output
        lang_detected = _detect_language(full_text)

        elapsed = round((time.monotonic() - start) * 1000, 2)

        return OCRPageResult(
            text=full_text,
            confidence=round(overall_confidence, 4),
            engine=OCREngine.TESSERACT,
            words=words,
            lines=lines,
            language_detected=lang_detected,
            processing_time_ms=elapsed,
        )

    except Exception as e:
        logger.error(f"Tesseract extraction failed: {e}")
        elapsed = round((time.monotonic() - start) * 1000, 2)

        # Fallback: simple text extraction
        try:
            simple_text = pytesseract.image_to_string(
                pil_image,
                lang=cfg.languages,
                config=tess_config,
            )
            return OCRPageResult(
                text=simple_text.strip(),
                confidence=0.3,
                engine=OCREngine.TESSERACT,
                processing_time_ms=elapsed,
            )
        except Exception as e2:
            logger.error(f"Tesseract fallback also failed: {e2}")
            return OCRPageResult(
                text="",
                confidence=0.0,
                engine=OCREngine.TESSERACT,
                processing_time_ms=elapsed,
            )


# ─────────────────────────────────────────────
# Word & Line Extraction
# ─────────────────────────────────────────────


def _extract_words(data: dict[str, Any]) -> list[OCRWord]:
    """Extract individual words with confidence and bounding boxes."""
    words: list[OCRWord] = []
    n_items = len(data.get("text", []))

    for i in range(n_items):
        text = str(data["text"][i]).strip()
        conf = int(data["conf"][i])

        if not text or conf < 0:
            continue

        words.append(OCRWord(
            text=text,
            confidence=round(conf / 100.0, 4),
            bbox=BoundingBox(
                x=int(data["left"][i]),
                y=int(data["top"][i]),
                w=int(data["width"][i]),
                h=int(data["height"][i]),
            ),
        ))

    return words


def _group_words_into_lines(
    words: list[OCRWord],
    data: dict[str, Any],
) -> list[OCRLine]:
    """
    Group words into lines based on Tesseract's block/paragraph/line numbers.
    """
    lines_dict: dict[tuple[int, int, int], list[int]] = {}
    n_items = len(data.get("text", []))

    for i in range(n_items):
        text = str(data["text"][i]).strip()
        conf = int(data["conf"][i])
        if not text or conf < 0:
            continue

        block = int(data["block_num"][i])
        par = int(data["par_num"][i])
        line = int(data["line_num"][i])
        key = (block, par, line)

        if key not in lines_dict:
            lines_dict[key] = []
        lines_dict[key].append(i)

    result: list[OCRLine] = []
    word_idx = 0

    for key in sorted(lines_dict.keys()):
        indices = lines_dict[key]
        line_words: list[OCRWord] = []

        for idx in indices:
            text = str(data["text"][idx]).strip()
            conf = int(data["conf"][idx])
            if not text or conf < 0:
                continue

            line_words.append(OCRWord(
                text=text,
                confidence=round(conf / 100.0, 4),
                bbox=BoundingBox(
                    x=int(data["left"][idx]),
                    y=int(data["top"][idx]),
                    w=int(data["width"][idx]),
                    h=int(data["height"][idx]),
                ),
            ))

        if not line_words:
            continue

        line_text = " ".join(w.text for w in line_words)
        line_conf = (
            sum(w.confidence for w in line_words) / len(line_words)
            if line_words
            else 0.0
        )

        # Compute line bounding box
        min_x = min(w.bbox.x for w in line_words)
        min_y = min(w.bbox.y for w in line_words)
        max_x = max(w.bbox.x + w.bbox.w for w in line_words)
        max_y = max(w.bbox.y + w.bbox.h for w in line_words)

        result.append(OCRLine(
            text=line_text,
            confidence=round(line_conf, 4),
            words=line_words,
            bbox=BoundingBox(
                x=min_x,
                y=min_y,
                w=max_x - min_x,
                h=max_y - min_y,
            ),
        ))

    return result


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────


def _select_psm(
    default_psm: int,
    content_type: ContentType,
    shape: tuple[int, ...],
) -> int:
    """
    Select the best PSM (Page Segmentation Mode) based on content type.

    PSM values:
      3 = Fully automatic page segmentation (default)
      4 = Assume single column of variable sizes
      6 = Assume a single uniform block of text
      7 = Treat as a single text line
      11 = Sparse text (find as much as possible)
      12 = Sparse text with OSD
    """
    h = shape[0]
    w = shape[1] if len(shape) > 1 else shape[0]

    # Very tall narrow region → single column
    if h > w * 3:
        return 4

    # Very wide short region → single line
    if w > h * 5 and h < 100:
        return 7

    # Handwritten content → sparse text works better
    if content_type == ContentType.HANDWRITTEN:
        return 6

    # Default: automatic page segmentation
    return default_psm


def _detect_language(text: str) -> str:
    """Simple language detection based on character analysis."""
    if not text:
        return "unknown"

    # Check for Devanagari characters (Hindi)
    devanagari_count = sum(
        1 for ch in text if "\u0900" <= ch <= "\u097F"
    )
    latin_count = sum(
        1 for ch in text if ch.isascii() and ch.isalpha()
    )

    total = devanagari_count + latin_count
    if total == 0:
        return "unknown"

    if devanagari_count > latin_count:
        return "hin"
    elif devanagari_count > 0:
        return "eng+hin"
    return "eng"
