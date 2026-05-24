"""
Atopsy — Entity Value Normalizer.

Normalizes entity values to canonical forms using rules from the
normalization layer. Records each transformation in the entity's
provenance chain for full audit traceability.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.logger import logger
from app.pipeline.structuring.schemas import (
    EntityType,
    EntityNormalizationStatus,
    StructuredEntity,
    TransformationStep,
)


# ─────────────────────────────────────────────
# Normalization Dictionaries
# ─────────────────────────────────────────────

_MANNER_OF_DEATH_MAP: dict[str, str] = {
    "natural": "NATURAL", "disease": "NATURAL",
    "accident": "ACCIDENTAL", "accidental": "ACCIDENTAL", "rta": "ACCIDENTAL",
    "suicide": "SUICIDE", "self-inflicted": "SUICIDE",
    "homicide": "HOMICIDE", "murder": "HOMICIDE",
    "undetermined": "UNDETERMINED", "pending": "UNDETERMINED",
}

_INJURY_TYPE_MAP: dict[str, str] = {
    "cut": "laceration", "slash": "laceration",
    "bruise": "contusion", "black eye": "contusion",
    "scrape": "abrasion", "graze": "abrasion",
    "broken bone": "fracture", "crack": "fracture",
    "stab": "puncture_wound", "pierce": "puncture_wound",
    "bullet wound": "gunshot_wound", "gsw": "gunshot_wound",
    "burn": "burn", "scald": "burn",
}

_GENDER_MAP: dict[str, str] = {
    "m": "Male", "male": "Male", "man": "Male",
    "f": "Female", "female": "Female", "woman": "Female",
}

_SUBSTANCE_MAP: dict[str, str] = {
    "ethyl alcohol": "ethanol", "alcohol": "ethanol", "etoh": "ethanol",
    "brown sugar": "diacetylmorphine", "smack": "diacetylmorphine",
    "heroin": "diacetylmorphine",
    "celphos": "aluminum_phosphide", "sulphas": "aluminum_phosphide",
    "rat poison": "aluminum_phosphide",
    "ganja": "cannabis", "bhang": "cannabis", "charas": "cannabis",
    "marijuana": "cannabis",
    "op compound": "organophosphate", "insecticide": "organophosphate",
    "kuchla": "strychnine", "nux vomica": "strychnine",
    "kaner": "nerium_oleander", "oleander": "nerium_oleander",
}


class ValueNormalizer:
    """
    Normalizes entity values to canonical forms.

    Applies type-specific normalization rules and records
    each transformation in the entity's provenance chain.
    """

    def normalize_entities(
        self,
        entities: list[StructuredEntity],
    ) -> list[StructuredEntity]:
        """
        Normalize all entity values.

        Args:
            entities: Entities with raw values.

        Returns:
            Entities with canonical_value set and provenance updated.
        """
        normalized: list[StructuredEntity] = []
        for entity in entities:
            try:
                result = self._normalize_entity(entity)
                normalized.append(result)
            except Exception as e:
                logger.warning(
                    f"Normalization failed for entity {entity.entity_id}: {e}"
                )
                entity.normalization_status = EntityNormalizationStatus.FAILED
                normalized.append(entity)

        count = sum(
            1 for e in normalized
            if e.normalization_status == EntityNormalizationStatus.NORMALIZED
        )
        logger.debug(
            f"ValueNormalizer: {count}/{len(normalized)} entities normalized"
        )
        return normalized

    def _normalize_entity(
        self,
        entity: StructuredEntity,
    ) -> StructuredEntity:
        """Apply type-specific normalization."""
        etype = entity.entity_type
        original = entity.canonical_value

        if etype == EntityType.MANNER_OF_DEATH:
            normalized = self._normalize_manner_of_death(original)
        elif etype == EntityType.INJURY:
            normalized = self._normalize_injury(original)
        elif etype == EntityType.DECEASED_INFO and entity.sub_type == "DECEASED_GENDER":
            normalized = self._normalize_gender(original)
        elif etype == EntityType.TOXICOLOGY_FINDING:
            normalized = self._normalize_substance(original)
        elif etype == EntityType.ANATOMICAL_REFERENCE:
            normalized = original.lower().strip()
        else:
            normalized = original.strip()

        if normalized != original:
            entity.canonical_value = normalized
            entity.normalization_status = EntityNormalizationStatus.NORMALIZED
            entity.provenance.transformations.append(TransformationStep(
                stage="value_normalization",
                rule=f"{entity.entity_type.value}_normalization",
                value_before=original,
                value_after=normalized,
                confidence_before=entity.confidence,
                confidence_after=entity.confidence,
            ))
        else:
            entity.normalization_status = EntityNormalizationStatus.PARTIALLY_NORMALIZED

        return entity

    def _normalize_manner_of_death(self, value: str) -> str:
        key = value.strip().lower()
        for term, canonical in _MANNER_OF_DEATH_MAP.items():
            if term in key:
                return canonical
        return value.strip()

    def _normalize_injury(self, value: str) -> str:
        lower = value.strip().lower()
        for term, canonical in _INJURY_TYPE_MAP.items():
            if term in lower:
                return value  # Keep original description, type is classified
        return value.strip()

    def _normalize_gender(self, value: str) -> str:
        return _GENDER_MAP.get(value.strip().lower(), value.strip())

    def _normalize_substance(self, value: str) -> str:
        lower = value.strip().lower()
        for term, canonical in _SUBSTANCE_MAP.items():
            if term in lower:
                return value.replace(term, canonical) if term != lower else canonical
        return value.strip()
