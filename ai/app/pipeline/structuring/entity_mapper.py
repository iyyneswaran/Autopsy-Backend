"""
Atopsy — Entity Mapper.

Maps ExtractedSpan objects (from Layer 3) to StructuredEntity objects
with UUID identifiers, entity type resolution, duplicate merging,
and initial provenance construction.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.core.logger import logger
from app.pipeline.extraction.schemas import ExtractedSpan, SourceSpan
from app.pipeline.structuring.schemas import (
    EntityType,
    EntityNormalizationStatus,
    EntityProvenance,
    StructuredEntity,
)


# Map from extraction entity type strings to canonical EntityType
_TYPE_MAP: dict[str, EntityType] = {
    "CASE_IDENTIFIER": EntityType.CASE_IDENTIFIER,
    "DECEASED_NAME": EntityType.DECEASED_INFO,
    "DECEASED_AGE": EntityType.DECEASED_INFO,
    "DECEASED_GENDER": EntityType.DECEASED_INFO,
    "CAUSE_OF_DEATH": EntityType.CAUSE_OF_DEATH,
    "MANNER_OF_DEATH": EntityType.MANNER_OF_DEATH,
    "TIME_OF_DEATH": EntityType.TIME_OF_DEATH,
    "EXAMINING_DOCTOR": EntityType.EXAMINER,
    "INJURY": EntityType.INJURY,
    "TOXICOLOGY_FINDING": EntityType.TOXICOLOGY_FINDING,
    "ANATOMICAL_REFERENCE": EntityType.ANATOMICAL_REFERENCE,
    "ORGAN_FINDING": EntityType.ORGAN_FINDING,
    "EXTERNAL_EXAMINATION": EntityType.EXTERNAL_EXAMINATION,
    "INTERNAL_EXAMINATION": EntityType.INTERNAL_EXAMINATION,
    "SCENE_REFERENCE": EntityType.SCENE_REFERENCE,
}


class EntityMapper:
    """
    Maps ExtractedSpan to StructuredEntity with deduplication.

    Resolves entity types, assigns UUIDs, builds initial provenance,
    and merges duplicates from multiple extractors.
    """

    def map_spans(
        self,
        spans: list[ExtractedSpan],
    ) -> list[StructuredEntity]:
        """
        Map extracted spans to structured entities.

        Args:
            spans: Extracted spans from Layer 3.

        Returns:
            List of StructuredEntity with unique IDs and provenance.
        """
        entities: list[StructuredEntity] = []

        for span in spans:
            entity = self._span_to_entity(span)
            if entity:
                entities.append(entity)

        # Merge duplicates from different extractors
        merged = self._merge_duplicates(entities)

        logger.debug(
            f"EntityMapper: {len(spans)} spans → {len(entities)} entities "
            f"→ {len(merged)} after merge"
        )
        return merged

    def _span_to_entity(self, span: ExtractedSpan) -> StructuredEntity | None:
        """Convert a single ExtractedSpan to a StructuredEntity."""
        entity_type = _TYPE_MAP.get(span.entity_type)
        if not entity_type:
            logger.warning(
                f"Unknown entity type: {span.entity_type}, skipping"
            )
            return None

        # Determine sub_type from span metadata or original entity type
        sub_type = span.metadata.get("sub_type", span.entity_type)

        provenance = EntityProvenance(
            source_spans=[span.source_span],
            extractor_id=span.extractor_id,
            extraction_method=span.extraction_method,
            extraction_confidence=span.confidence,
            original_text=span.source_span.raw_text,
            document_page=span.source_span.page,
        )

        return StructuredEntity(
            entity_id=str(uuid.uuid4()),
            entity_type=entity_type,
            canonical_value=span.value,
            raw_value=span.value,
            category=entity_type.value,
            sub_type=sub_type,
            confidence=span.confidence,
            provenance=provenance,
            normalization_status=EntityNormalizationStatus.RAW,
            metadata=span.metadata,
        )

    def _merge_duplicates(
        self,
        entities: list[StructuredEntity],
    ) -> list[StructuredEntity]:
        """
        Merge duplicate entities from different extractors.

        When two entities have the same type and similar values,
        keep the highest-confidence version with merged provenance.
        """
        if len(entities) <= 1:
            return entities

        # Group by entity_type + sub_type
        groups: dict[str, list[StructuredEntity]] = {}
        for ent in entities:
            key = f"{ent.entity_type.value}:{ent.sub_type}:{ent.metadata.get('assertion_status', 'EXTRACTED_ASSERTION')}:{ent.provenance.document_page}"
            groups.setdefault(key, []).append(ent)

        merged: list[StructuredEntity] = []
        for key, group in groups.items():
            if len(group) == 1:
                merged.append(group[0])
                continue

            # Sort by confidence descending
            group.sort(key=lambda e: e.confidence, reverse=True)

            # Check for same-value duplicates from different extractors
            seen_values: dict[str, StructuredEntity] = {}
            for ent in group:
                val_key = ent.canonical_value.strip().lower()
                if val_key in seen_values:
                    # Merge provenance from duplicate
                    existing = seen_values[val_key]
                    existing.provenance.source_spans.extend(
                        ent.provenance.source_spans
                    )
                    existing.confidence = max(
                        existing.confidence, ent.confidence
                    )
                else:
                    seen_values[val_key] = ent

            merged.extend(seen_values.values())

        return merged
