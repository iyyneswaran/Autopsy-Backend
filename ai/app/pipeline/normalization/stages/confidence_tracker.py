"""
Atopsy — Confidence Tracking Through Normalization.

Tracks how confidence scores degrade or improve through
each normalization transformation. Provides audit trail
of all confidence changes with transformation types.
"""

from __future__ import annotations

from typing import Any


class TransformationType:
    """Constants for transformation types and their confidence impacts."""
    EXACT_MATCH = "EXACT_MATCH"          # No degradation
    FUZZY_MATCH = "FUZZY_MATCH"          # 5-15% degradation
    INFERRED = "INFERRED"                # 20-40% degradation
    DEFAULT_VALUE = "DEFAULT_VALUE"      # 50%+ degradation
    VALIDATED = "VALIDATED"              # May improve confidence
    ONTOLOGY_MAPPED = "ONTOLOGY_MAPPED"  # Slight improvement

    DEGRADATION: dict[str, float] = {
        "EXACT_MATCH": 1.0,
        "FUZZY_MATCH": 0.9,
        "INFERRED": 0.7,
        "DEFAULT_VALUE": 0.5,
        "VALIDATED": 1.05,
        "ONTOLOGY_MAPPED": 1.02,
    }


class ConfidenceTransformation:
    """Record of a single confidence transformation."""

    __slots__ = (
        "field", "stage", "transformation_type",
        "confidence_before", "confidence_after",
        "rule", "detail",
    )

    def __init__(
        self,
        field: str,
        stage: str,
        transformation_type: str,
        confidence_before: float,
        confidence_after: float,
        rule: str = "",
        detail: str = "",
    ) -> None:
        self.field = field
        self.stage = stage
        self.transformation_type = transformation_type
        self.confidence_before = confidence_before
        self.confidence_after = confidence_after
        self.rule = rule
        self.detail = detail

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "stage": self.stage,
            "transformation_type": self.transformation_type,
            "confidence_before": round(self.confidence_before, 4),
            "confidence_after": round(self.confidence_after, 4),
            "rule": self.rule,
            "detail": self.detail,
        }


class ConfidenceTracker:
    """
    Tracks confidence scores through normalization pipeline stages.

    Each field maintains a running confidence that degrades or improves
    based on the transformations applied to it.
    """

    def __init__(self) -> None:
        self._field_confidence: dict[str, float] = {}
        self._transformations: list[ConfidenceTransformation] = []

    def set_initial(self, field: str, confidence: float) -> None:
        """Set the initial confidence for a field."""
        self._field_confidence[field] = max(0.0, min(1.0, confidence))

    def record_transformation(
        self,
        field: str,
        stage: str,
        transformation_type: str,
        rule: str = "",
        detail: str = "",
        override_confidence: float | None = None,
    ) -> float:
        """
        Record a transformation and update the field's confidence.

        Args:
            field: The field being transformed.
            stage: Which pipeline stage applied this.
            transformation_type: Type of transformation (from TransformationType).
            rule: The rule or pattern that was applied.
            detail: Human-readable description.
            override_confidence: If set, use this instead of computing.

        Returns:
            The new confidence value.
        """
        before = self._field_confidence.get(field, 1.0)

        if override_confidence is not None:
            after = max(0.0, min(1.0, override_confidence))
        else:
            factor = TransformationType.DEGRADATION.get(
                transformation_type, 0.9
            )
            after = max(0.0, min(1.0, before * factor))

        self._field_confidence[field] = after

        self._transformations.append(ConfidenceTransformation(
            field=field,
            stage=stage,
            transformation_type=transformation_type,
            confidence_before=before,
            confidence_after=after,
            rule=rule,
            detail=detail,
        ))

        return after

    def get_field_confidence(self, field: str) -> float:
        """Get the current confidence for a field."""
        return self._field_confidence.get(field, 0.0)

    def get_all_confidences(self) -> dict[str, float]:
        """Get all field confidences."""
        return {
            k: round(v, 4) for k, v in self._field_confidence.items()
        }

    def get_composite_confidence(self) -> float:
        """
        Compute overall composite confidence as weighted average
        of all tracked fields.
        """
        if not self._field_confidence:
            return 0.0
        values = list(self._field_confidence.values())
        return round(sum(values) / len(values), 4)

    def get_audit_trail(self) -> list[dict[str, Any]]:
        """Get the full audit trail of transformations."""
        return [t.to_dict() for t in self._transformations]

    def get_stage_summary(self) -> dict[str, dict[str, Any]]:
        """Get a summary of confidence changes per stage."""
        stages: dict[str, dict[str, Any]] = {}
        for t in self._transformations:
            if t.stage not in stages:
                stages[t.stage] = {
                    "transformations": 0,
                    "total_degradation": 0.0,
                    "fields_affected": set(),
                }
            stages[t.stage]["transformations"] += 1
            stages[t.stage]["total_degradation"] += (
                t.confidence_before - t.confidence_after
            )
            stages[t.stage]["fields_affected"].add(t.field)

        # Convert sets to counts for serialization
        return {
            stage: {
                "transformations": info["transformations"],
                "total_degradation": round(info["total_degradation"], 4),
                "fields_affected": len(info["fields_affected"]),
            }
            for stage, info in stages.items()
        }

    @property
    def transformation_count(self) -> int:
        return len(self._transformations)

    def to_dict(self) -> dict[str, Any]:
        return {
            "field_confidences": self.get_all_confidences(),
            "composite_confidence": self.get_composite_confidence(),
            "transformation_count": self.transformation_count,
            "stage_summary": self.get_stage_summary(),
            "audit_trail": self.get_audit_trail(),
        }
