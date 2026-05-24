"""
Atopsy — Provenance Chain Tracker.

Builds and manages provenance chains for forensic entities,
linking each entity back to its source OCR text through
a recorded sequence of transformations.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.pipeline.extraction.schemas import ExtractedSpan, SourceSpan
from app.pipeline.structuring.schemas import (
    EntityProvenance,
    TransformationStep,
    StructuredEntity,
)


class ProvenanceTracker:
    """
    Builds and validates provenance chains for structured entities.

    Every entity must trace back to its OCR source through a
    complete chain of transformation steps.
    """

    @staticmethod
    def build_provenance(
        entity: StructuredEntity,
        span: ExtractedSpan,
    ) -> EntityProvenance:
        """
        Build initial provenance from an extracted span.

        Args:
            entity: The structured entity.
            span: The source extracted span.

        Returns:
            EntityProvenance with source span and extraction info.
        """
        return EntityProvenance(
            source_spans=[span.source_span],
            extractor_id=span.extractor_id,
            extraction_method=span.extraction_method,
            extraction_confidence=span.confidence,
            original_text=span.source_span.raw_text,
            document_page=(
                span.source_span.page
                if span.source_span.page > 0
                else None
            ),
        )

    @staticmethod
    def record_transformation(
        provenance: EntityProvenance,
        stage: str,
        rule: str,
        before: str,
        after: str,
        conf_before: float,
        conf_after: float,
    ) -> EntityProvenance:
        """
        Record a transformation step in the provenance chain.

        Args:
            provenance: Existing provenance to extend.
            stage: Pipeline stage that performed the transformation.
            rule: Rule or pattern that was applied.
            before: Value before transformation.
            after: Value after transformation.
            conf_before: Confidence before.
            conf_after: Confidence after.

        Returns:
            Updated EntityProvenance.
        """
        step = TransformationStep(
            stage=stage,
            rule=rule,
            value_before=before,
            value_after=after,
            confidence_before=conf_before,
            confidence_after=conf_after,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        provenance.transformations.append(step)
        return provenance

    @staticmethod
    def compute_provenance_depth(provenance: EntityProvenance) -> int:
        """Count the number of transformation steps in the chain."""
        return len(provenance.transformations)

    @staticmethod
    def validate_provenance(provenance: EntityProvenance) -> list[str]:
        """
        Validate a provenance chain for completeness.

        Returns:
            List of warning strings (empty if valid).
        """
        warnings: list[str] = []

        if not provenance.source_spans:
            warnings.append("No source spans in provenance")

        if not provenance.extractor_id:
            warnings.append("Missing extractor_id")

        if not provenance.original_text:
            warnings.append("Missing original_text")

        if provenance.extraction_confidence <= 0.0:
            warnings.append("Zero or negative extraction_confidence")

        for i, step in enumerate(provenance.transformations):
            if not step.stage:
                warnings.append(f"Transformation {i}: missing stage")
            if step.confidence_after < 0 or step.confidence_after > 1.0:
                warnings.append(
                    f"Transformation {i}: confidence_after out of range"
                )

        return warnings

    def enrich_all(
        self,
        entities: list[StructuredEntity],
    ) -> list[StructuredEntity]:
        """
        Validate and enrich provenance for all entities.

        Adds provenance warnings to entity validation_errors.
        """
        for entity in entities:
            warnings = self.validate_provenance(entity.provenance)
            if warnings:
                entity.validation_errors.extend(
                    [f"provenance: {w}" for w in warnings]
                )
        return entities
