"""
Atopsy — Base NLP Extractor Interface.

Abstract base class for all forensic NLP extractors.
Concrete extractors (regex, Gemini, spaCy) implement this
interface to participate in the extraction pipeline.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.pipeline.extraction.schemas import ExtractedSpan


class BaseExtractor(ABC):
    """
    Abstract base for forensic document NLP extractors.

    Every extractor declares which entity types it supports and
    implements the ``extract`` method that returns source-span-tagged
    results.
    """

    extractor_id: str = "base"
    supported_entity_types: list[str] = []

    @abstractmethod
    def extract(
        self,
        text: str,
        context: dict[str, Any] | None = None,
    ) -> list[ExtractedSpan]:
        """
        Extract forensic entities from text.

        Args:
            text: Full document text or section text.
            context: Optional extraction context (sections, language, etc.).

        Returns:
            List of ExtractedSpan with source provenance.
        """
        ...

    def supports(self, entity_type: str) -> bool:
        """Check if this extractor handles a given entity type."""
        return entity_type in self.supported_entity_types
