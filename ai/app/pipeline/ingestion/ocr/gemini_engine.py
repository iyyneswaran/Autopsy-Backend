"""
Atopsy — Gemini Vision OCR Engine.

Uses Google Gemini Vision API for handwriting recognition
and structured extraction from forensic documents.
Forensic-specific prompt engineering for Indian autopsy reports.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import time
from typing import Any

import numpy as np
from PIL import Image

from app.core.logger import logger
from app.pipeline.ingestion.ocr.schemas import (
    GeminiConfig,
    OCREngine,
    OCRPageResult,
)


# ─────────────────────────────────────────────
# Prompts
# ─────────────────────────────────────────────

_TEXT_EXTRACTION_PROMPT = """You are an expert forensic document reader specializing in Indian medico-legal documents.

Extract ALL text from this document image with maximum accuracy.

Rules:
1. Preserve the original layout and line structure
2. If text is handwritten, transcribe it as accurately as possible
3. Maintain section headers, numbering, and formatting
4. For illegible portions, write [ILLEGIBLE] with your best guess in parentheses
5. If text is in Hindi (Devanagari), transcribe it in the original script
6. Preserve medical terminology, abbreviations, and measurements exactly
7. Include all stamps, signatures, dates, and case numbers

Return ONLY the extracted text, nothing else."""


_STRUCTURED_EXTRACTION_PROMPT = """You are an expert forensic document analyst specializing in Indian autopsy and post-mortem reports.

Extract structured information from this document image and return as JSON.

Required fields (use null if not found):
{
  "case_number": "string",
  "deceased_name": "string",
  "deceased_age": "string",
  "deceased_gender": "string",
  "date_of_examination": "string",
  "time_of_examination": "string",
  "examining_doctor": "string",
  "cause_of_death": "string",
  "manner_of_death": "string",
  "time_of_death": "string",
  "external_examination": "string (full text)",
  "internal_examination": "string (full text)",
  "injuries": [
    {"type": "string", "location": "string", "description": "string", "dimensions": "string"}
  ],
  "toxicology": [
    {"substance": "string", "result": "string", "concentration": "string"}
  ],
  "opinion": "string",
  "identification_marks": ["string"]
}

Important:
- Extract data from both printed AND handwritten portions
- Handle Hindi/English mixed content
- For measurements, preserve original units
- Return ONLY valid JSON, no commentary"""


def extract_text(
    image_bytes: bytes,
    config: GeminiConfig | None = None,
) -> OCRPageResult:
    """
    Extract text from an image using Gemini Vision API.

    Args:
        image_bytes: Raw image bytes (PNG/JPEG).
        config: Gemini configuration options.

    Returns:
        OCRPageResult with extracted text and estimated confidence.
    """
    cfg = config or GeminiConfig()
    start = time.monotonic()

    try:
        import google.generativeai as genai

        api_key = os.environ.get("GOOGLE_API_KEY", "")
        if not api_key:
            logger.warning("GOOGLE_API_KEY not set, Gemini OCR unavailable")
            return OCRPageResult(
                text="",
                confidence=0.0,
                engine=OCREngine.GEMINI,
                processing_time_ms=round((time.monotonic() - start) * 1000, 2),
            )

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(cfg.model_name)

        # Encode image
        b64_image = base64.b64encode(image_bytes).decode("utf-8")
        mime_type = _detect_mime(image_bytes)

        # Retry loop
        last_error: Exception | None = None
        for attempt in range(cfg.max_retries):
            try:
                response = model.generate_content(
                    [
                        _TEXT_EXTRACTION_PROMPT,
                        {"mime_type": mime_type, "data": b64_image},
                    ],
                    generation_config={
                        "temperature": cfg.temperature,
                        "max_output_tokens": 8192,
                    },
                )

                text = response.text.strip() if response.text else ""
                confidence = _estimate_confidence(text)

                elapsed = round((time.monotonic() - start) * 1000, 2)

                return OCRPageResult(
                    text=text,
                    confidence=confidence,
                    engine=OCREngine.GEMINI,
                    processing_time_ms=elapsed,
                )

            except Exception as e:
                last_error = e
                logger.warning(
                    f"Gemini OCR attempt {attempt + 1}/{cfg.max_retries} "
                    f"failed: {e}"
                )
                if attempt < cfg.max_retries - 1:
                    delay = cfg.retry_delay_seconds * (2 ** attempt)
                    time.sleep(delay)

        # All retries exhausted
        elapsed = round((time.monotonic() - start) * 1000, 2)
        logger.error(f"Gemini OCR failed after {cfg.max_retries} retries: {last_error}")
        return OCRPageResult(
            text="",
            confidence=0.0,
            engine=OCREngine.GEMINI,
            processing_time_ms=elapsed,
        )

    except ImportError:
        logger.warning("google-generativeai not installed")
        return OCRPageResult(
            text="",
            confidence=0.0,
            engine=OCREngine.GEMINI,
            processing_time_ms=round((time.monotonic() - start) * 1000, 2),
        )

    except Exception as e:
        elapsed = round((time.monotonic() - start) * 1000, 2)
        logger.error(f"Gemini OCR unexpected error: {e}")
        return OCRPageResult(
            text="",
            confidence=0.0,
            engine=OCREngine.GEMINI,
            processing_time_ms=elapsed,
        )


def extract_structured(
    image_bytes: bytes,
    config: GeminiConfig | None = None,
) -> dict[str, Any]:
    """
    Extract structured forensic data from a document image.

    Returns a dict matching the structured extraction schema.
    Falls back to empty dict on failure.
    """
    cfg = config or GeminiConfig()

    try:
        import google.generativeai as genai

        api_key = os.environ.get("GOOGLE_API_KEY", "")
        if not api_key:
            return {}

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(cfg.model_name)

        b64_image = base64.b64encode(image_bytes).decode("utf-8")
        mime_type = _detect_mime(image_bytes)

        for attempt in range(cfg.max_retries):
            try:
                response = model.generate_content(
                    [
                        _STRUCTURED_EXTRACTION_PROMPT,
                        {"mime_type": mime_type, "data": b64_image},
                    ],
                    generation_config={
                        "temperature": 0.05,
                        "max_output_tokens": 4096,
                    },
                )

                raw = response.text.strip() if response.text else ""
                return _parse_json_response(raw)

            except Exception as e:
                logger.warning(
                    f"Gemini structured extraction attempt "
                    f"{attempt + 1}/{cfg.max_retries} failed: {e}"
                )
                if attempt < cfg.max_retries - 1:
                    time.sleep(cfg.retry_delay_seconds * (2 ** attempt))

        return {}

    except ImportError:
        return {}
    except Exception as e:
        logger.error(f"Gemini structured extraction error: {e}")
        return {}


def extract_text_from_full_text(
    full_text: str,
    config: GeminiConfig | None = None,
) -> dict[str, Any]:
    """
    Extract structured forensic fields from already-extracted OCR text
    using Gemini's text understanding capabilities.
    """
    cfg = config or GeminiConfig()

    prompt = f"""You are an expert forensic document analyst specializing in Indian autopsy reports.

Given the following OCR-extracted text from a forensic document, extract structured data as JSON.

TEXT:
---
{full_text[:6000]}
---

Return JSON with these fields (use null if not found):
{{
  "case_number": "string",
  "deceased_name": "string",
  "deceased_age": "string",
  "deceased_gender": "string",
  "date_of_examination": "string",
  "examining_doctor": "string",
  "cause_of_death": "string",
  "manner_of_death": "string",
  "time_of_death": "string",
  "injuries": [{{"type": "string", "location": "string", "description": "string", "dimensions": "string"}}],
  "toxicology": [{{"substance": "string", "result": "string", "concentration": "string"}}],
  "opinion": "string"
}}

Return ONLY valid JSON."""

    try:
        import google.generativeai as genai

        api_key = os.environ.get("GOOGLE_API_KEY", "")
        if not api_key:
            return {}

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(cfg.model_name)

        response = model.generate_content(
            prompt,
            generation_config={
                "temperature": 0.05,
                "max_output_tokens": 4096,
            },
        )

        raw = response.text.strip() if response.text else ""
        return _parse_json_response(raw)

    except Exception as e:
        logger.error(f"Gemini text extraction error: {e}")
        return {}


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────


def _estimate_confidence(text: str) -> float:
    """
    Estimate confidence of Gemini OCR output based on quality indicators.
    Since Gemini doesn't provide confidence scores, we estimate from
    output structure and content quality.
    """
    if not text:
        return 0.0

    score = 0.5  # Base confidence

    # Longer, more structured text = higher confidence
    word_count = len(text.split())
    if word_count > 100:
        score += 0.15
    elif word_count > 50:
        score += 0.10
    elif word_count > 20:
        score += 0.05

    # Presence of structured elements
    if any(marker in text.lower() for marker in [
        "cause of death", "post-mortem", "autopsy",
        "examination", "findings", "opinion",
    ]):
        score += 0.10

    # Fewer [ILLEGIBLE] markers = higher confidence
    illegible_count = text.count("[ILLEGIBLE]")
    if illegible_count == 0:
        score += 0.10
    elif illegible_count > 5:
        score -= 0.15

    # Presence of numbers/measurements
    import re
    measurements = re.findall(r"\d+\.?\d*\s*(?:cm|mm|kg|gm|ml|mg)", text)
    if measurements:
        score += 0.05

    return round(max(0.1, min(0.95, score)), 4)


def _parse_json_response(raw: str) -> dict[str, Any]:
    """Parse JSON from Gemini response, handling markdown code blocks."""
    if not raw:
        return {}

    # Strip markdown code fences
    cleaned = raw.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to find JSON object in the text
        start_idx = cleaned.find("{")
        end_idx = cleaned.rfind("}")
        if start_idx >= 0 and end_idx > start_idx:
            try:
                return json.loads(cleaned[start_idx:end_idx + 1])
            except json.JSONDecodeError:
                pass

        logger.warning("Failed to parse Gemini JSON response")
        return {}


def _detect_mime(image_bytes: bytes) -> str:
    """Detect image MIME type from magic bytes."""
    if image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    elif image_bytes[:2] == b"\xff\xd8":
        return "image/jpeg"
    elif image_bytes[:4] in (b"II*\x00", b"MM\x00*"):
        return "image/tiff"
    elif image_bytes[:2] == b"BM":
        return "image/bmp"
    return "image/png"


def numpy_to_bytes(image: np.ndarray) -> bytes:
    """Convert numpy array to PNG bytes for Gemini API."""
    pil_image = Image.fromarray(image)
    buffer = io.BytesIO()
    pil_image.save(buffer, format="PNG")
    return buffer.getvalue()
