"""
Atopsy — Forensic Entity Structuring Schemas (Layer 4).

Pydantic models for the canonical forensic entity graph output.
Covers entity types, provenance, transformation tracking,
structured entities, relationships, and the top-level
ForensicEntityGraph.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from app.pipeline.extraction.schemas import SourceSpan


# ─────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────


class EntityType(str, enum.Enum):
    """Canonical forensic entity types."""

    CASE_IDENTIFIER = "CASE_IDENTIFIER"
    DECEASED_INFO = "DECEASED_INFO"
    INJURY = "INJURY"
    CAUSE_OF_DEATH = "CAUSE_OF_DEATH"
    MANNER_OF_DEATH = "MANNER_OF_DEATH"
    TIME_OF_DEATH = "TIME_OF_DEATH"
    ANATOMICAL_REFERENCE = "ANATOMICAL_REFERENCE"
    TOXICOLOGY_FINDING = "TOXICOLOGY_FINDING"
    EXAMINER = "EXAMINER"
    SCENE_REFERENCE = "SCENE_REFERENCE"
    ORGAN_FINDING = "ORGAN_FINDING"
    EXTERNAL_EXAMINATION = "EXTERNAL_EXAMINATION"
    INTERNAL_EXAMINATION = "INTERNAL_EXAMINATION"


class EntityNormalizationStatus(str, enum.Enum):
    """Normalization status of a structured entity."""

    RAW = "RAW"
    NORMALIZED = "NORMALIZED"
    PARTIALLY_NORMALIZED = "PARTIALLY_NORMALIZED"
    FAILED = "FAILED"
    VALIDATED = "VALIDATED"


class RelationshipType(str, enum.Enum):
    """Types of relationships between entities."""

    LOCATED_AT = "LOCATED_AT"
    CAUSED_BY = "CAUSED_BY"
    ASSOCIATED_WITH = "ASSOCIATED_WITH"
    EXAMINED_BY = "EXAMINED_BY"
    CONTAINS = "CONTAINS"
    TEMPORAL_SEQUENCE = "TEMPORAL_SEQUENCE"


# ─────────────────────────────────────────────
# Provenance & Transformation
# ─────────────────────────────────────────────


class TransformationStep(BaseModel):
    """A single step in the transformation audit trail."""

    stage: str
    rule: str = ""
    value_before: str = ""
    value_after: str = ""
    confidence_before: float = 0.0
    confidence_after: float = 0.0
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class EntityProvenance(BaseModel):
    """Full traceability chain for a structured entity."""

    source_spans: list[SourceSpan] = Field(default_factory=list)
    extractor_id: str = ""
    extraction_method: str = ""
    extraction_confidence: float = Field(0.0, ge=0.0, le=1.0)
    transformations: list[TransformationStep] = Field(default_factory=list)
    original_text: str = ""
    document_page: int | None = None


# ─────────────────────────────────────────────
# Structured Entity
# ─────────────────────────────────────────────


class StructuredEntity(BaseModel):
    """
    A canonical forensic entity with provenance and normalization.

    This is the core output unit of the entity structuring layer.
    """

    entity_id: str = ""
    entity_type: EntityType
    canonical_value: str = ""
    raw_value: str = ""
    category: str = ""
    sub_type: str = ""
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    provenance: EntityProvenance = Field(default_factory=EntityProvenance)
    normalization_status: EntityNormalizationStatus = (
        EntityNormalizationStatus.RAW
    )
    metadata: dict[str, Any] = Field(default_factory=dict)
    validation_errors: list[str] = Field(default_factory=list)


# ─────────────────────────────────────────────
# Entity Relationships
# ─────────────────────────────────────────────


class EntityRelationship(BaseModel):
    """An edge between two entities in the forensic entity graph."""

    source_entity_id: str
    target_entity_id: str
    relationship_type: RelationshipType
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ─────────────────────────────────────────────
# Graph Metrics
# ─────────────────────────────────────────────


class EntityGraphMetrics(BaseModel):
    """Quality metrics for the entity graph."""

    total_entities: int = 0
    entity_type_counts: dict[str, int] = Field(default_factory=dict)
    average_confidence: float = Field(0.0, ge=0.0, le=1.0)
    normalization_coverage: float = Field(0.0, ge=0.0, le=1.0)
    validation_pass_rate: float = Field(0.0, ge=0.0, le=1.0)
    provenance_depth_avg: float = 0.0


class StructuringStageReport(BaseModel):
    """Report for a single structuring pipeline stage."""

    stage: str
    status: str = "completed"
    duration_ms: float = 0.0
    entities_processed: int = 0
    detail: str = ""
    error: str | None = None


# ─────────────────────────────────────────────
# Top-Level Graph
# ─────────────────────────────────────────────


class ForensicEntityGraph(BaseModel):
    """
    Top-level output of the Forensic Entity Structuring layer.

    Contains categorized entity collections, relationships,
    graph metrics, and processing reports.
    """

    evidence_file_id: str = ""
    schema_version: str = "1.0.0"
    entities: dict[str, list[StructuredEntity]] = Field(
        default_factory=dict
    )
    relationships: list[EntityRelationship] = Field(default_factory=list)
    metrics: EntityGraphMetrics = Field(default_factory=EntityGraphMetrics)
    stage_reports: list[StructuringStageReport] = Field(default_factory=list)
    processing_time_ms: float = 0.0
    processed_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
