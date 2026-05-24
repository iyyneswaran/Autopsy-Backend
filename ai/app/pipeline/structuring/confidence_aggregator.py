"""
Atopsy — Confidence Aggregation for Entity Structuring.

Aggregates confidence scores across the entity pipeline:
OCR confidence × extraction confidence × normalization factor.
Consistent with ConfidenceTracker from the normalization layer.
"""

from __future__ import annotations

from app.core.logger import logger
from app.pipeline.structuring.schemas import (
    EntityNormalizationStatus,
    StructuredEntity,
)


# Normalization factor per status
_NORM_FACTORS: dict[EntityNormalizationStatus, float] = {
    EntityNormalizationStatus.VALIDATED: 1.0,
    EntityNormalizationStatus.NORMALIZED: 1.0,
    EntityNormalizationStatus.PARTIALLY_NORMALIZED: 0.9,
    EntityNormalizationStatus.RAW: 0.7,
    EntityNormalizationStatus.FAILED: 0.5,
}


class ConfidenceAggregator:
    """
    Aggregates confidence scores across the entity pipeline.

    Final confidence = ocr_confidence × extraction_confidence × norm_factor.
    """

    def aggregate(
        self,
        entities: list[StructuredEntity],
        ocr_confidence: float = 1.0,
    ) -> list[StructuredEntity]:
        """
        Compute final confidence for each entity.

        Args:
            entities: Entities to score.
            ocr_confidence: Overall OCR confidence for the document.

        Returns:
            Entities with aggregated confidence scores.
        """
        for entity in entities:
            extraction_conf = entity.provenance.extraction_confidence
            norm_factor = _NORM_FACTORS.get(
                entity.normalization_status, 0.7
            )
            final = round(
                max(0.0, min(1.0, ocr_confidence * extraction_conf * norm_factor)),
                4,
            )
            entity.confidence = final

        return entities

    @staticmethod
    def compute_graph_confidence(
        entities: list[StructuredEntity],
    ) -> float:
        """
        Compute overall graph confidence as weighted average.

        Args:
            entities: All entities in the graph.

        Returns:
            Graph-level confidence score.
        """
        if not entities:
            return 0.0
        confs = [e.confidence for e in entities if e.confidence > 0]
        if not confs:
            return 0.0
        return round(sum(confs) / len(confs), 4)
