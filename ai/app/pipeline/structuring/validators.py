"""
Atopsy — Entity Validation Rules.

Type-specific validation for structured forensic entities.
Validates values, formats, and cross-entity consistency.
Updates normalization_status to VALIDATED on success.
"""

from __future__ import annotations

import re
from typing import Any

from app.core.logger import logger
from app.pipeline.structuring.schemas import (
    EntityType,
    EntityNormalizationStatus,
    StructuredEntity,
)


_VALID_MANNERS = {"NATURAL", "ACCIDENTAL", "SUICIDE", "HOMICIDE", "UNDETERMINED"}
_VALID_GENDERS = {"Male", "Female", "Unknown"}


class EntityValidator:
    """
    Validates structured forensic entities.

    Applies type-specific validation rules and updates
    normalization_status to VALIDATED on success.
    """

    def validate_all(
        self,
        entities: list[StructuredEntity],
    ) -> list[StructuredEntity]:
        """
        Validate all entities and update their status.

        Args:
            entities: Entities to validate.

        Returns:
            Entities with validation_errors and updated status.
        """
        validated_count = 0
        for entity in entities:
            errors = self.validate_entity(entity)
            entity.validation_errors.extend(errors)
            if not errors and entity.normalization_status in (
                EntityNormalizationStatus.NORMALIZED,
                EntityNormalizationStatus.PARTIALLY_NORMALIZED,
            ):
                entity.normalization_status = EntityNormalizationStatus.VALIDATED
                validated_count += 1

        logger.debug(
            f"EntityValidator: {validated_count}/{len(entities)} entities "
            f"passed validation"
        )
        return entities

    def validate_entity(self, entity: StructuredEntity) -> list[str]:
        """
        Validate a single entity and return error messages.

        Args:
            entity: Entity to validate.

        Returns:
            List of error strings (empty if valid).
        """
        errors: list[str] = []

        # Universal checks
        if not entity.canonical_value or not entity.canonical_value.strip():
            errors.append("Empty canonical_value")

        if entity.confidence < 0 or entity.confidence > 1.0:
            errors.append(f"Confidence out of range: {entity.confidence}")

        # Type-specific checks
        etype = entity.entity_type

        if etype == EntityType.DECEASED_INFO:
            errors.extend(self._validate_deceased(entity))
        elif etype == EntityType.MANNER_OF_DEATH:
            errors.extend(self._validate_manner_of_death(entity))
        elif etype == EntityType.TOXICOLOGY_FINDING:
            errors.extend(self._validate_toxicology(entity))
        elif etype == EntityType.TIME_OF_DEATH:
            errors.extend(self._validate_time_of_death(entity))

        return errors

    def _validate_deceased(self, entity: StructuredEntity) -> list[str]:
        errors: list[str] = []
        sub = entity.sub_type

        if sub == "DECEASED_AGE":
            try:
                age = int(entity.canonical_value)
                if age < 0 or age > 150:
                    errors.append(f"Age out of range (0-150): {age}")
            except (ValueError, TypeError):
                errors.append(
                    f"Non-numeric age: {entity.canonical_value}"
                )

        if sub == "DECEASED_GENDER":
            if entity.canonical_value not in _VALID_GENDERS:
                errors.append(
                    f"Invalid gender: {entity.canonical_value}, "
                    f"expected one of {_VALID_GENDERS}"
                )

        if sub == "DECEASED_NAME":
            if len(entity.canonical_value.strip()) < 2:
                errors.append("Name too short")

        return errors

    def _validate_manner_of_death(self, entity: StructuredEntity) -> list[str]:
        errors: list[str] = []
        if entity.canonical_value.upper() not in _VALID_MANNERS:
            errors.append(
                f"Invalid manner of death: {entity.canonical_value}, "
                f"expected one of {_VALID_MANNERS}"
            )
        return errors

    def _validate_toxicology(self, entity: StructuredEntity) -> list[str]:
        errors: list[str] = []
        val = entity.canonical_value
        if len(val) < 3:
            errors.append("Toxicology finding too short")
        return errors

    def _validate_time_of_death(self, entity: StructuredEntity) -> list[str]:
        errors: list[str] = []
        val = entity.canonical_value
        if len(val) < 3:
            errors.append("Time of death value too short")
        return errors
