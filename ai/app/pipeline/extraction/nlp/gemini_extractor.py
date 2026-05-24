"""
Atopsy — Model-Assisted Forensic NLP Extractor (Gemini).

Uses Gemini Vision API for structured extraction from forensic
documents. Serves as a fallback/enrichment layer when rule-based
extraction yields low confidence or for handwritten text regions.
"""

from __future__ import annotations

import json
import time
from typing import Any

from app.core.config import settings
from app.core.logger import logger
from app.pipeline.extraction.nlp.base import BaseExtractor
from app.pipeline.extraction.schemas import ExtractedSpan, SourceSpan


# Gemini extraction prompt for Indian medico-legal documents
_FORENSIC_PROMPT = """You are analyzing an Indian medico-legal document (autopsy/post-mortem report, FIR, or toxicology report).

Extract ALL of the following entities if present. Return a JSON array where each item has:
- "entity_type": one of CASE_IDENTIFIER, DECEASED_NAME, DECEASED_AGE, DECEASED_GENDER, CAUSE_OF_DEATH, MANNER_OF_DEATH, TIME_OF_DEATH, EXAMINING_DOCTOR, INJURY, TOXICOLOGY_FINDING, ANATOMICAL_REFERENCE, ORGAN_FINDING
- "value": the extracted value
- "confidence": 0.0-1.0

If an entity is not found, omit it. Return ONLY valid JSON.

Document text:
{text}"""


class GeminiExtractor(BaseExtractor):
    """
    Model-assisted forensic NLP extractor using Gemini API.

    Sends document text to Gemini with a structured forensic prompt
    and parses the response into ExtractedSpan objects. Includes
    retry logic and graceful degradation.
    """

    extractor_id = "gemini_vision_v1"
    supported_entity_types = [
        "CASE_IDENTIFIER", "DECEASED_NAME", "DECEASED_AGE",
        "DECEASED_GENDER", "CAUSE_OF_DEATH", "MANNER_OF_DEATH",
        "TIME_OF_DEATH", "EXAMINING_DOCTOR", "INJURY",
        "TOXICOLOGY_FINDING", "ANATOMICAL_REFERENCE", "ORGAN_FINDING",
    ]

    def __init__(
        self,
        max_retries: int = 3,
        retry_delay: float = 2.0,
    ) -> None:
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def extract(
        self,
        text: str,
        context: dict[str, Any] | None = None,
    ) -> list[ExtractedSpan]:
        """
        Extract entities using Gemini API.

        Returns empty list if API is unavailable or extraction fails.
        Never raises — graceful degradation is a design requirement.
        """
        if not text or len(text.strip()) < 10:
            return []

        api_key = getattr(settings, "GOOGLE_API_KEY", "")
        if not api_key:
            logger.warning(
                "GeminiExtractor: No GOOGLE_API_KEY configured, skipping"
            )
            return []

        # Truncate very long texts
        truncated = text[:15000] if len(text) > 15000 else text

        for attempt in range(1, self.max_retries + 1):
            try:
                raw_response = self._call_gemini(truncated, api_key)
                entities = self._parse_response(raw_response)
                logger.info(
                    f"GeminiExtractor: extracted {len(entities)} entities "
                    f"on attempt {attempt}"
                )
                return entities
            except Exception as e:
                logger.warning(
                    f"GeminiExtractor attempt {attempt}/{self.max_retries} "
                    f"failed: {e}"
                )
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay * attempt)

        logger.error("GeminiExtractor: all retries exhausted, returning empty")
        return []

    def _call_gemini(self, text: str, api_key: str) -> str:
        """
        Call Gemini API with the forensic extraction prompt.

        Uses google.generativeai if available, otherwise falls back
        to HTTP requests.
        """
        try:
            import google.generativeai as genai

            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-2.0-flash")
            prompt = _FORENSIC_PROMPT.format(text=text)
            response = model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(
                    temperature=0.1,
                    max_output_tokens=4096,
                ),
            )
            return response.text if response.text else ""
        except ImportError:
            logger.warning(
                "google-generativeai not installed, Gemini extraction unavailable"
            )
            return ""
        except Exception as e:
            raise RuntimeError(f"Gemini API call failed: {e}") from e

    def _parse_response(self, raw: str) -> list[ExtractedSpan]:
        """Parse Gemini JSON response into ExtractedSpan objects."""
        if not raw:
            return []

        # Strip markdown code fences if present
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:])
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            # Try to find JSON array in the response
            start = cleaned.find("[")
            end = cleaned.rfind("]")
            if start >= 0 and end > start:
                try:
                    data = json.loads(cleaned[start : end + 1])
                except json.JSONDecodeError:
                    logger.warning("GeminiExtractor: could not parse JSON response")
                    return []
            else:
                return []

        if not isinstance(data, list):
            data = [data]

        spans: list[ExtractedSpan] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            entity_type = item.get("entity_type", "")
            value = item.get("value", "")
            confidence = float(item.get("confidence", 0.6))

            if entity_type and value:
                spans.append(ExtractedSpan(
                    entity_type=entity_type,
                    value=str(value),
                    source_span=SourceSpan(raw_text=str(value)[:200]),
                    confidence=min(1.0, max(0.0, confidence)),
                    extractor_id=self.extractor_id,
                    extraction_method="model_assisted",
                    metadata={"gemini_raw": item},
                ))

        return spans
